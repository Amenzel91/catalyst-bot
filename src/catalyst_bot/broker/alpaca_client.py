"""
Alpaca Broker Client

This module implements the BrokerInterface for Alpaca Markets.

Alpaca API Documentation: https://alpaca.markets/docs/api-references/trading-api/

Features:
- REST API integration for orders, positions, and account
- WebSocket streaming for real-time updates (optional)
- Paper trading support
- Bracket order support
- Extended hours trading
- Rate limiting and retry logic
- Comprehensive error handling

Configuration:
- ALPACA_API_KEY: API key from Alpaca
- ALPACA_API_SECRET: API secret from Alpaca
- ALPACA_BASE_URL: Base URL (paper vs live)
"""

import asyncio
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from .broker_interface import (
    Account,
    AccountStatus,
    BracketOrder,
    BracketOrderParams,
    BrokerAuthenticationError,
    BrokerConnectionError,
    BrokerError,
    BrokerInterface,
    InsufficientFundsError,
    Order,
    OrderNotFoundError,
    OrderRejectedError,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    RateLimitError,
    TimeInForce,
)

logger = logging.getLogger(__name__)


class AlpacaBrokerClient(BrokerInterface):
    """
    Alpaca Markets broker implementation.

    This client provides a complete implementation of the BrokerInterface
    for Alpaca Markets, including paper trading support.

    Rate Limits (as of 2024):
    - 200 requests per minute for most endpoints
    - 60 requests per minute for market data
    """

    # Alpaca API URLs
    LIVE_BASE_URL = "https://api.alpaca.markets"
    PAPER_BASE_URL = "https://paper-api.alpaca.markets"

    # API endpoints
    ACCOUNT_ENDPOINT = "/v2/account"
    POSITIONS_ENDPOINT = "/v2/positions"
    ORDERS_ENDPOINT = "/v2/orders"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper_trading: bool = True,
        base_url: Optional[str] = None,
        config: Optional[Dict] = None,
    ):
        """
        Initialize Alpaca broker client.

        Args:
            api_key: Alpaca API key (or set ALPACA_API_KEY env var)
            api_secret: Alpaca API secret (or set ALPACA_API_SECRET env var)
            paper_trading: Use paper trading (default: True)
            base_url: Override base URL
            config: Additional configuration dictionary
        """
        # Initialize parent
        super().__init__(config or {})

        # Get credentials
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET", "")

        if not self.api_key or not self.api_secret:
            raise BrokerAuthenticationError(
                "Alpaca API credentials not provided. "
                "Set ALPACA_API_KEY and ALPACA_API_SECRET environment variables."
            )

        # Set base URL
        if base_url:
            self.base_url = base_url
        elif paper_trading:
            self.base_url = self.PAPER_BASE_URL
        else:
            self.base_url = self.LIVE_BASE_URL

        self.paper_trading = paper_trading

        # HTTP session (initialized in connect())
        self.session: Optional[ClientSession] = None
        self._connected = False

        # Rate limiting
        self._rate_limit_remaining = 200
        self._rate_limit_reset = None
        self._request_count = 0

        # Retry configuration
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1.0)

        self.logger.info(
            f"Initialized Alpaca client (paper_trading={paper_trading}, "
            f"base_url={self.base_url})"
        )

    # ========================================================================
    # Connection Management
    # ========================================================================

    async def connect(self) -> bool:
        """
        Establish connection to Alpaca API.

        Returns:
            True if connection successful

        Raises:
            BrokerConnectionError: If connection fails
            BrokerAuthenticationError: If authentication fails
        """
        try:
            # Create HTTP session
            timeout = ClientTimeout(total=30, connect=10)
            self.session = ClientSession(
                timeout=timeout,
                headers=self._get_headers(),
            )

            # Test connection by fetching account
            try:
                await self._test_connection()
            except Exception:
                # Clean up session if connection test fails
                if self.session:
                    await self.session.close()
                    self.session = None
                raise

            self._connected = True
            self.logger.info("Successfully connected to Alpaca API")
            return True

        except BrokerAuthenticationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to connect to Alpaca: {e}")
            raise BrokerConnectionError(f"Connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from Alpaca API and clean up resources."""
        if self.session:
            await self.session.close()
            self.session = None

        self._connected = False
        self.logger.info("Disconnected from Alpaca API")

    async def is_connected(self) -> bool:
        """Check if currently connected to Alpaca."""
        return self._connected and self.session is not None

    async def _test_connection(self) -> None:
        """
        Test connection by making a simple API call.

        Raises:
            BrokerAuthenticationError: If authentication fails
            BrokerConnectionError: If connection fails
        """
        try:
            # TODO: Make a test request to /v2/account
            # TODO: Parse response and verify authentication
            # TODO: Handle authentication errors specifically

            url = self._build_url(self.ACCOUNT_ENDPOINT)
            await self._request("GET", url)

            # If we get here, connection is successful
            self.logger.debug("Connection test successful")

        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                raise BrokerAuthenticationError("Invalid API credentials")
            raise BrokerConnectionError(f"Connection test failed: {e}") from e

    # ========================================================================
    # HTTP Request Handling
    # ========================================================================

    def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for Alpaca API requests.

        Returns:
            Dictionary of HTTP headers
        """
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Content-Type": "application/json",
        }

    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from endpoint.

        Args:
            endpoint: API endpoint (e.g., "/v2/account")

        Returns:
            Full URL
        """
        return urljoin(self.base_url, endpoint)

    async def _request(
        self,
        method: str,
        url: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        retry_count: int = 0,
    ) -> Dict:
        """
        Make HTTP request to Alpaca API with retry logic.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            url: Full URL
            json_data: JSON body data
            params: Query parameters
            retry_count: Current retry attempt

        Returns:
            Response data as dictionary

        Raises:
            BrokerConnectionError: If not connected
            RateLimitError: If rate limit exceeded
            BrokerError: If request fails
        """
        if not self.session:
            raise BrokerConnectionError("Not connected to Alpaca API")

        try:
            # TODO: Check rate limits before making request
            # TODO: Add exponential backoff if retrying

            # Make request
            async with self.session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
            ) as response:
                # TODO: Update rate limit tracking from response headers
                # Alpaca sends: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
                self._update_rate_limits(response.headers)

                # Increment request counter
                self._request_count += 1

                # Handle rate limiting
                if response.status == 429:
                    self.logger.warning("Rate limit exceeded, retrying...")
                    if retry_count < self.max_retries:
                        await asyncio.sleep(self.retry_delay * (2**retry_count))
                        return await self._request(
                            method, url, json_data, params, retry_count + 1
                        )
                    raise RateLimitError("Rate limit exceeded")

                # Handle authentication errors
                if response.status == 401:
                    raise BrokerAuthenticationError("Authentication failed")

                # Handle other errors
                if response.status >= 400:
                    error_text = await response.text()
                    self.logger.error(
                        f"Alpaca API error {response.status}: {error_text}"
                    )

                    # Parse error message
                    try:
                        error_data = await response.json()
                        error_message = error_data.get("message", error_text)
                    except Exception:
                        error_message = error_text

                    # Retry on server errors
                    if response.status >= 500 and retry_count < self.max_retries:
                        await asyncio.sleep(self.retry_delay * (2**retry_count))
                        return await self._request(
                            method, url, json_data, params, retry_count + 1
                        )

                    raise BrokerError(f"API request failed: {error_message}")

                # Parse successful response
                return await response.json()

        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP request failed: {e}")

            # Retry on connection errors
            if retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2**retry_count))
                return await self._request(
                    method, url, json_data, params, retry_count + 1
                )

            raise BrokerConnectionError(f"Request failed: {e}") from e

    def _update_rate_limits(self, headers: Dict) -> None:
        """
        Update rate limit tracking from response headers.

        Args:
            headers: Response headers from Alpaca API
        """
        # TODO: Parse rate limit headers
        # X-RateLimit-Remaining: number of requests remaining
        # X-RateLimit-Reset: timestamp when limit resets

        if "X-RateLimit-Remaining" in headers:
            try:
                self._rate_limit_remaining = int(headers["X-RateLimit-Remaining"])
            except (ValueError, TypeError):
                pass

        if "X-RateLimit-Reset" in headers:
            try:
                self._rate_limit_reset = int(headers["X-RateLimit-Reset"])
            except (ValueError, TypeError):
                pass

    # ========================================================================
    # Account Information
    # ========================================================================

    async def get_account(self) -> Account:
        """
        Get current account information from Alpaca.

        Returns:
            Account object with current account details

        Raises:
            BrokerConnectionError: If not connected
            BrokerError: If request fails
        """
        url = self._build_url(self.ACCOUNT_ENDPOINT)
        data = await self._request("GET", url)

        # TODO: Convert Alpaca account response to Account dataclass
        # Alpaca response fields:
        # - id, account_number, status
        # - cash, portfolio_value, equity, buying_power
        # - multiplier (leverage)
        # - pattern_day_trader
        # - trading_blocked, transfers_blocked, account_blocked
        # - created_at

        return self._parse_account(data)

    def _parse_account(self, data: Dict) -> Account:
        """
        Parse Alpaca account response to Account dataclass.

        Args:
            data: Raw account data from Alpaca API

        Returns:
            Account object
        """
        # TODO: Implement parsing logic
        # TODO: Convert string values to Decimal
        # TODO: Parse timestamps
        # TODO: Map status values

        return Account(
            account_id=data.get("id", ""),
            account_number=data.get("account_number", ""),
            status=self._parse_account_status(data.get("status", "ACTIVE")),
            cash=Decimal(str(data.get("cash", "0"))),
            portfolio_value=Decimal(str(data.get("portfolio_value", "0"))),
            equity=Decimal(str(data.get("equity", "0"))),
            buying_power=Decimal(str(data.get("buying_power", "0"))),
            initial_margin=Decimal(str(data.get("initial_margin", "0"))),
            maintenance_margin=Decimal(str(data.get("maintenance_margin", "0"))),
            leverage=Decimal(str(data.get("multiplier", "1"))),
            pattern_day_trader=data.get("pattern_day_trader", False),
            trading_blocked=data.get("trading_blocked", False),
            transfers_blocked=data.get("transfers_blocked", False),
            account_blocked=data.get("account_blocked", False),
            created_at=self._parse_timestamp(data.get("created_at")),
            updated_at=datetime.now(),
            metadata={"raw_data": data},
        )

    async def get_buying_power(self) -> Decimal:
        """Get current buying power."""
        account = await self.get_account()
        return account.buying_power

    # ========================================================================
    # Position Management
    # ========================================================================

    async def get_positions(self) -> List[Position]:
        """
        Get all open positions from Alpaca.

        Returns:
            List of Position objects
        """
        url = self._build_url(self.POSITIONS_ENDPOINT)
        data = await self._request("GET", url)

        # TODO: Parse array of positions
        # TODO: Convert each position to Position dataclass

        return [self._parse_position(pos) for pos in data]

    async def get_position(self, ticker: str) -> Optional[Position]:
        """
        Get position for specific ticker.

        Args:
            ticker: Stock symbol

        Returns:
            Position object if position exists, None otherwise
        """
        url = self._build_url(f"{self.POSITIONS_ENDPOINT}/{ticker}")

        try:
            data = await self._request("GET", url)
            return self._parse_position(data)
        except BrokerError as e:
            # Alpaca returns 404 if position doesn't exist
            if "404" in str(e) or "not found" in str(e).lower():
                return None
            raise

    async def close_position(
        self,
        ticker: str,
        quantity: Optional[int] = None,
    ) -> Order:
        """
        Close an existing position.

        Args:
            ticker: Stock symbol
            quantity: Quantity to close (None = close entire position)

        Returns:
            Order object for the closing order
        """
        # TODO: Alpaca has a dedicated close position endpoint
        # DELETE /v2/positions/{symbol}
        # Can specify qty parameter to partially close

        url = self._build_url(f"{self.POSITIONS_ENDPOINT}/{ticker}")
        params = {"qty": str(quantity)} if quantity else None

        data = await self._request("DELETE", url, params=params)

        # Response is the closing order
        return self._parse_order(data)

    def _parse_position(self, data: Dict) -> Position:
        """
        Parse Alpaca position response to Position dataclass.

        Args:
            data: Raw position data from Alpaca API

        Returns:
            Position object
        """
        # TODO: Implement parsing logic
        # Alpaca position fields:
        # - symbol, qty, side (long/short)
        # - avg_entry_price, current_price
        # - cost_basis, market_value
        # - unrealized_pl, unrealized_plpc
        # - qty_available

        qty = int(data.get("qty", "0"))
        side = PositionSide.LONG if data.get("side") == "long" else PositionSide.SHORT

        return Position(
            ticker=data.get("symbol", ""),
            side=side,
            quantity=abs(qty),
            available_quantity=abs(int(data.get("qty_available", "0"))),
            entry_price=Decimal(str(data.get("avg_entry_price", "0"))),
            current_price=Decimal(str(data.get("current_price", "0"))),
            cost_basis=Decimal(str(data.get("cost_basis", "0"))),
            market_value=Decimal(str(data.get("market_value", "0"))),
            unrealized_pnl=Decimal(str(data.get("unrealized_pl", "0"))),
            unrealized_pnl_pct=Decimal(str(data.get("unrealized_plpc", "0"))),
            opened_at=datetime.now(),  # Alpaca doesn't provide this
            updated_at=datetime.now(),
            metadata={"raw_data": data},
        )

    # ========================================================================
    # Order Management
    # ========================================================================

    async def place_order(
        self,
        ticker: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        extended_hours: bool = False,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """
        Place a single order with Alpaca.

        Args:
            ticker: Stock symbol
            side: Order side (buy/sell)
            quantity: Number of shares
            order_type: Type of order
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            time_in_force: Time in force
            extended_hours: Allow extended hours trading
            client_order_id: Client-specified order ID

        Returns:
            Order object with order details
        """
        # TODO: Build order request payload
        # TODO: Validate parameters
        # TODO: Submit to Alpaca API
        # TODO: Handle errors (insufficient funds, invalid parameters, etc.)

        url = self._build_url(self.ORDERS_ENDPOINT)

        # Build request payload
        payload = {
            "symbol": ticker,
            "qty": quantity,
            "side": side.value,
            "type": self._map_order_type(order_type),
            "time_in_force": self._map_time_in_force(time_in_force),
            "extended_hours": extended_hours,
        }

        # Add price parameters
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)

        # Add client order ID if provided
        if client_order_id:
            payload["client_order_id"] = client_order_id

        # Submit order
        try:
            data = await self._request("POST", url, json_data=payload)
            return self._parse_order(data)
        except BrokerError as e:
            # Check for specific error types
            error_msg = str(e).lower()
            if "insufficient" in error_msg or "buying power" in error_msg:
                raise InsufficientFundsError(str(e)) from e
            if "rejected" in error_msg or "invalid" in error_msg:
                raise OrderRejectedError(str(e)) from e
            raise

    async def place_bracket_order(
        self,
        params: BracketOrderParams,
    ) -> BracketOrder:
        """
        Place a bracket order with Alpaca.

        Alpaca supports native bracket orders via the order_class parameter.

        Args:
            params: Bracket order parameters

        Returns:
            BracketOrder object with all three orders
        """
        # TODO: Build bracket order request
        # Alpaca bracket order format:
        # - order_class: "bracket"
        # - take_profit: { limit_price: "..." }
        # - stop_loss: { stop_price: "...", limit_price: "..." (optional) }

        url = self._build_url(self.ORDERS_ENDPOINT)

        payload = {
            "symbol": params.ticker,
            "qty": params.quantity,
            "side": params.side.value,
            "type": self._map_order_type(params.entry_type),
            "time_in_force": self._map_time_in_force(params.time_in_force),
            "order_class": "bracket",
            "take_profit": {
                "limit_price": str(params.take_profit_price),
            },
            "stop_loss": {
                "stop_price": str(params.stop_loss_price),
            },
            "extended_hours": params.extended_hours,
        }

        # Add entry limit price if specified
        if params.entry_limit_price is not None:
            payload["limit_price"] = str(params.entry_limit_price)

        # Add client order ID if provided
        if params.client_order_id:
            payload["client_order_id"] = params.client_order_id

        # Submit bracket order
        try:
            data = await self._request("POST", url, json_data=payload)

            # TODO: Alpaca returns the entry order with legs[] array
            # Parse entry order and leg orders
            entry_order = self._parse_order(data)

            # Extract leg orders from response
            legs = data.get("legs", [])
            stop_loss_order = None
            take_profit_order = None

            for leg in legs:
                leg_order = self._parse_order(leg)
                if leg.get("stop_price"):
                    stop_loss_order = leg_order
                else:
                    take_profit_order = leg_order

            if not stop_loss_order or not take_profit_order:
                raise BrokerError("Bracket order missing stop loss or take profit")

            return BracketOrder(
                entry_order=entry_order,
                stop_loss_order=stop_loss_order,
                take_profit_order=take_profit_order,
            )

        except BrokerError as e:
            error_msg = str(e).lower()
            if "insufficient" in error_msg or "buying power" in error_msg:
                raise InsufficientFundsError(str(e)) from e
            if "rejected" in error_msg or "invalid" in error_msg:
                raise OrderRejectedError(str(e)) from e
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: Alpaca order ID

        Returns:
            True if cancelled successfully
        """
        url = self._build_url(f"{self.ORDERS_ENDPOINT}/{order_id}")

        try:
            await self._request("DELETE", url)
            return True
        except BrokerError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise OrderNotFoundError(f"Order {order_id} not found") from e
            # Order might already be filled
            if "unable to cancel" in str(e).lower():
                self.logger.warning(f"Unable to cancel order {order_id}: {e}")
                return False
            raise

    async def cancel_all_orders(self) -> int:
        """
        Cancel all open orders.

        Returns:
            Number of orders cancelled
        """
        # TODO: Alpaca has a dedicated endpoint to cancel all orders
        # DELETE /v2/orders

        url = self._build_url(self.ORDERS_ENDPOINT)

        try:
            data = await self._request("DELETE", url)
            # Response is array of cancelled orders
            return len(data) if isinstance(data, list) else 0
        except BrokerError as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            return 0

    async def get_order(self, order_id: str) -> Order:
        """
        Get details of a specific order.

        Args:
            order_id: Alpaca order ID

        Returns:
            Order object with current order details
        """
        url = self._build_url(f"{self.ORDERS_ENDPOINT}/{order_id}")

        try:
            data = await self._request("GET", url)
            return self._parse_order(data)
        except BrokerError as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise OrderNotFoundError(f"Order {order_id} not found") from e
            raise

    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        limit: int = 100,
    ) -> List[Order]:
        """
        Get list of orders.

        Args:
            status: Filter by order status (None = open orders only)
            limit: Maximum number of orders to return

        Returns:
            List of Order objects
        """
        url = self._build_url(self.ORDERS_ENDPOINT)

        # Build query parameters
        params = {
            "limit": limit,
        }

        # TODO: Map our OrderStatus to Alpaca status values
        if status:
            params["status"] = self._map_order_status_for_query(status)
        else:
            params["status"] = "open"  # Default to open orders

        data = await self._request("GET", url, params=params)

        # Parse orders
        return [self._parse_order(order) for order in data]

    def _parse_order(self, data: Dict) -> Order:
        """
        Parse Alpaca order response to Order dataclass.

        Args:
            data: Raw order data from Alpaca API

        Returns:
            Order object
        """
        # TODO: Implement parsing logic
        # Alpaca order fields:
        # - id, client_order_id
        # - symbol, side, type, qty, filled_qty
        # - limit_price, stop_price, filled_avg_price
        # - time_in_force, status
        # - submitted_at, filled_at, cancelled_at, updated_at
        # - extended_hours
        # - legs[] (for bracket orders)

        return Order(
            order_id=data.get("id", ""),
            client_order_id=data.get("client_order_id"),
            ticker=data.get("symbol", ""),
            side=OrderSide(data.get("side", "buy")),
            order_type=self._parse_order_type(data.get("type", "market")),
            quantity=int(data.get("qty", "0")),
            filled_quantity=int(data.get("filled_qty", "0")),
            limit_price=self._parse_decimal(data.get("limit_price")),
            stop_price=self._parse_decimal(data.get("stop_price")),
            filled_avg_price=self._parse_decimal(data.get("filled_avg_price")),
            time_in_force=self._parse_time_in_force(data.get("time_in_force", "day")),
            status=self._parse_order_status(data.get("status", "pending")),
            submitted_at=self._parse_timestamp(data.get("submitted_at")),
            filled_at=self._parse_timestamp(data.get("filled_at")),
            cancelled_at=self._parse_timestamp(data.get("cancelled_at")),
            updated_at=self._parse_timestamp(data.get("updated_at")),
            extended_hours=data.get("extended_hours", False),
            metadata={"raw_data": data},
        )

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def _map_order_type(self, order_type: OrderType) -> str:
        """Map our OrderType to Alpaca order type."""
        mapping = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP: "stop",
            OrderType.STOP_LIMIT: "stop_limit",
            OrderType.TRAILING_STOP: "trailing_stop",
        }
        return mapping.get(order_type, "market")

    def _parse_order_type(self, alpaca_type: str) -> OrderType:
        """Parse Alpaca order type to our OrderType."""
        mapping = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
            "trailing_stop": OrderType.TRAILING_STOP,
        }
        return mapping.get(alpaca_type, OrderType.MARKET)

    def _map_time_in_force(self, tif: TimeInForce) -> str:
        """Map our TimeInForce to Alpaca time in force."""
        mapping = {
            TimeInForce.DAY: "day",
            TimeInForce.GTC: "gtc",
            TimeInForce.IOC: "ioc",
            TimeInForce.FOK: "fok",
        }
        return mapping.get(tif, "day")

    def _parse_time_in_force(self, alpaca_tif: str) -> TimeInForce:
        """Parse Alpaca time in force to our TimeInForce."""
        mapping = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK,
        }
        return mapping.get(alpaca_tif, TimeInForce.DAY)

    def _parse_order_status(self, alpaca_status: str) -> OrderStatus:
        """Parse Alpaca order status to our OrderStatus."""
        mapping = {
            "new": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "accepted": OrderStatus.SUBMITTED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "expired": OrderStatus.EXPIRED,
            "replaced": OrderStatus.CANCELLED,
            "pending_cancel": OrderStatus.SUBMITTED,
            "pending_replace": OrderStatus.SUBMITTED,
            "rejected": OrderStatus.REJECTED,
        }
        return mapping.get(alpaca_status, OrderStatus.PENDING)

    def _map_order_status_for_query(self, status: OrderStatus) -> str:
        """Map our OrderStatus to Alpaca status query parameter."""
        # Alpaca status query values: open, closed, all
        if status in {
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        }:
            return "open"
        elif status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        }:
            return "closed"
        return "all"

    def _parse_account_status(self, alpaca_status: str) -> AccountStatus:
        """Parse Alpaca account status to our AccountStatus."""
        mapping = {
            "ACTIVE": AccountStatus.ACTIVE,
            "ACCOUNT_CLOSED": AccountStatus.CLOSED,
            "ACCOUNT_SUSPENDED": AccountStatus.SUSPENDED,
        }
        return mapping.get(alpaca_status, AccountStatus.ACTIVE)

    def _parse_timestamp(self, ts_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO 8601 timestamp string to datetime."""
        if not ts_str:
            return None

        try:
            # TODO: Handle different timestamp formats
            # Alpaca uses ISO 8601: "2021-01-01T12:00:00.000000Z"
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"Failed to parse timestamp '{ts_str}': {e}")
            return None

    def _parse_decimal(self, value: Optional[str]) -> Optional[Decimal]:
        """Parse string to Decimal, returning None if invalid."""
        if value is None:
            return None

        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return None

    async def health_check(self) -> Dict:
        """Perform health check on Alpaca connection."""
        result = {
            "connected": await self.is_connected(),
            "authenticated": False,
            "latency_ms": 0.0,
            "rate_limit_remaining": self._rate_limit_remaining,
            "last_error": None,
        }

        if result["connected"]:
            try:
                # Measure latency with account request
                loop = asyncio.get_running_loop()
                start = loop.time()
                await self.get_account()
                end = loop.time()

                result["authenticated"] = True
                result["latency_ms"] = (end - start) * 1000

            except Exception as e:
                result["last_error"] = str(e)

        return result


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    """
    Example usage of AlpacaBrokerClient.

    This demonstrates how to use the Alpaca broker client.
    """

    async def demo():
        """Demo function showing Alpaca broker usage"""

        # Initialize Alpaca client (paper trading)
        broker = AlpacaBrokerClient(
            api_key=os.getenv("ALPACA_API_KEY"),
            api_secret=os.getenv("ALPACA_API_SECRET"),
            paper_trading=True,
        )

        try:
            # Connect to Alpaca
            await broker.connect()
            print("Connected to Alpaca")

            # Get account info
            account = await broker.get_account()
            print("\nAccount Info:")
            print(f"  Cash: ${account.cash}")
            print(f"  Buying Power: ${account.buying_power}")
            print(f"  Portfolio Value: ${account.portfolio_value}")
            print(f"  Status: {account.status}")

            # Get positions
            positions = await broker.get_positions()
            print(f"\nPositions: {len(positions)}")
            for pos in positions:
                print(f"  {pos.ticker}: {pos.quantity} shares @ ${pos.entry_price}")
                print(f"    Current: ${pos.current_price}, P&L: ${pos.unrealized_pnl}")

            # Place a market order
            print("\nPlacing market order for AAPL...")
            order = await broker.place_order(
                ticker="AAPL",
                side=OrderSide.BUY,
                quantity=1,
                order_type=OrderType.MARKET,
            )
            print(f"  Order placed: {order.order_id}")
            print(f"  Status: {order.status}")

            # Place a bracket order
            print("\nPlacing bracket order for TSLA...")
            bracket = await broker.place_bracket_order(
                BracketOrderParams(
                    ticker="TSLA",
                    side=OrderSide.BUY,
                    quantity=1,
                    entry_type=OrderType.LIMIT,
                    entry_limit_price=Decimal("200.00"),
                    stop_loss_price=Decimal("190.00"),
                    take_profit_price=Decimal("220.00"),
                    time_in_force=TimeInForce.GTC,
                )
            )
            print(f"  Entry order: {bracket.entry_order.order_id}")
            print(f"  Stop loss: {bracket.stop_loss_order.order_id}")
            print(f"  Take profit: {bracket.take_profit_order.order_id}")

            # Get open orders
            orders = await broker.get_orders()
            print(f"\nOpen Orders: {len(orders)}")
            for order in orders:
                print(
                    f"  {order.ticker} {order.side} {order.quantity} @ {order.status}"
                )

            # Health check
            health = await broker.health_check()
            print("\nHealth Check:")
            print(f"  Connected: {health['connected']}")
            print(f"  Latency: {health['latency_ms']:.2f}ms")
            print(f"  Rate Limit Remaining: {health['rate_limit_remaining']}")

        except Exception as e:
            print(f"Error: {e}")

        finally:
            # Disconnect
            await broker.disconnect()
            print("\nDisconnected from Alpaca")

    # Run demo
    asyncio.run(demo())
