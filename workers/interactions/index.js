/**
 * Cloudflare Worker for Discord Interaction Callbacks
 * ====================================================
 *
 * This worker handles Discord interaction callbacks for the Catalyst Bot.
 * It verifies Discord signatures, handles PING verification, button clicks,
 * and slash commands.
 *
 * Environment Variables Required:
 * - DISCORD_PUBLIC_KEY: Discord application public key for signature verification
 * - DISCORD_BOT_TOKEN: Discord bot token for API calls
 *
 * Interaction Types:
 * - Type 1: PING (Discord verification)
 * - Type 2: APPLICATION_COMMAND (slash commands)
 * - Type 3: MESSAGE_COMPONENT (button clicks)
 */

/**
 * Discord Interaction Types
 */
const InteractionType = {
  PING: 1,
  APPLICATION_COMMAND: 2,
  MESSAGE_COMPONENT: 3,
};

/**
 * Discord Interaction Response Types
 */
const InteractionResponseType = {
  PONG: 1,
  CHANNEL_MESSAGE_WITH_SOURCE: 4,
  DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE: 5,
  DEFERRED_UPDATE_MESSAGE: 6,
  UPDATE_MESSAGE: 7,
};

/**
 * Main fetch handler for Cloudflare Worker
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Health check endpoint
    if (url.pathname === '/health' && request.method === 'GET') {
      return new Response(JSON.stringify({ status: 'healthy' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Root endpoint - info page
    if (url.pathname === '/' && request.method === 'GET') {
      return new Response(
        `
<!DOCTYPE html>
<html>
<head>
  <title>Catalyst Bot Interaction Server</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
    h1 { color: #5865F2; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
    .endpoint { margin: 20px 0; padding: 15px; background: #f9f9f9; border-left: 4px solid #5865F2; }
  </style>
</head>
<body>
  <h1>Catalyst Bot Interaction Server</h1>
  <p>Server is running on Cloudflare Workers!</p>

  <div class="endpoint">
    <strong>Interaction Endpoint:</strong> <code>POST /interactions</code>
    <p>Handles Discord interaction callbacks (buttons, slash commands)</p>
  </div>

  <div class="endpoint">
    <strong>Health Check:</strong> <code>GET /health</code>
    <p>Returns server health status</p>
  </div>

  <p><em>Powered by Cloudflare Workers</em></p>
</body>
</html>
        `,
        {
          status: 200,
          headers: { 'Content-Type': 'text/html' },
        }
      );
    }

    // Discord interactions endpoint
    if (url.pathname === '/interactions' && request.method === 'POST') {
      return handleInteraction(request, env);
    }

    // 404 for unknown routes
    return new Response('Not Found', { status: 404 });
  },
};

/**
 * Handle Discord interaction requests
 */
async function handleInteraction(request, env) {
  try {
    // Get Discord public key from environment
    const PUBLIC_KEY = env.DISCORD_PUBLIC_KEY;

    if (!PUBLIC_KEY) {
      console.error('DISCORD_PUBLIC_KEY not configured');
      return jsonResponse({ error: 'Server configuration error' }, 500);
    }

    // Verify Discord signature
    const signature = request.headers.get('X-Signature-Ed25519');
    const timestamp = request.headers.get('X-Signature-Timestamp');
    const body = await request.clone().text();

    if (!signature || !timestamp) {
      console.error('Missing signature headers');
      return jsonResponse({ error: 'Invalid request' }, 401);
    }

    const isValid = await verifyDiscordSignature(
      signature,
      timestamp,
      body,
      PUBLIC_KEY
    );

    if (!isValid) {
      console.error('Invalid Discord signature');
      return jsonResponse({ error: 'Invalid signature' }, 401);
    }

    // Parse interaction data
    const interaction = JSON.parse(body);
    const interactionType = interaction.type;

    console.log(`Received interaction type: ${interactionType}`);

    // Handle PING (Discord endpoint verification)
    if (interactionType === InteractionType.PING) {
      console.log('Responding to PING with PONG');
      return jsonResponse({ type: InteractionResponseType.PONG });
    }

    // Handle APPLICATION_COMMAND (slash commands)
    if (interactionType === InteractionType.APPLICATION_COMMAND) {
      console.log('Handling APPLICATION_COMMAND');
      const response = await handleSlashCommand(interaction, env);
      return jsonResponse(response);
    }

    // Handle MESSAGE_COMPONENT (button clicks)
    if (interactionType === InteractionType.MESSAGE_COMPONENT) {
      console.log('Handling MESSAGE_COMPONENT');
      const response = await handleButtonClick(interaction, env);
      return jsonResponse(response);
    }

    // Unknown interaction type
    console.warn(`Unknown interaction type: ${interactionType}`);
    return jsonResponse({
      type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
      data: {
        content: 'Unknown interaction type',
        flags: 64, // Ephemeral
      },
    });
  } catch (error) {
    console.error('Error handling interaction:', error);
    return jsonResponse({
      type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
      data: {
        content: 'An error occurred processing your request.',
        flags: 64, // Ephemeral
      },
    });
  }
}

/**
 * Verify Discord signature using Ed25519
 */
async function verifyDiscordSignature(signature, timestamp, body, publicKey) {
  try {
    // Convert hex strings to Uint8Array
    const signatureBytes = hexToUint8Array(signature);
    const publicKeyBytes = hexToUint8Array(publicKey);

    // Create message to verify (timestamp + body)
    const message = new TextEncoder().encode(timestamp + body);

    // Import public key
    const key = await crypto.subtle.importKey(
      'raw',
      publicKeyBytes,
      {
        name: 'Ed25519',
        namedCurve: 'Ed25519',
      },
      false,
      ['verify']
    );

    // Verify signature
    const isValid = await crypto.subtle.verify(
      'Ed25519',
      key,
      signatureBytes,
      message
    );

    return isValid;
  } catch (error) {
    console.error('Signature verification error:', error);
    return false;
  }
}

/**
 * Handle slash command interactions
 */
async function handleSlashCommand(interaction, env) {
  try {
    const commandName = interaction.data?.name || '';
    const options = interaction.data?.options || [];

    console.log(`Slash command: ${commandName}`);

    // Parse subcommands (e.g., /admin report)
    let subcommand = null;
    let commandOptions = options;

    if (options.length > 0 && options[0].type === 1) {
      // SUB_COMMAND
      subcommand = options[0].name;
      commandOptions = options[0].options || [];
    }

    // Route to appropriate handler
    if (commandName === 'admin') {
      return handleAdminCommand(subcommand, commandOptions, interaction, env);
    } else if (commandName === 'check') {
      return handleCheckCommand(commandOptions, interaction, env);
    } else if (commandName === 'research') {
      return handleResearchCommand(commandOptions, interaction, env);
    } else if (commandName === 'ask') {
      return handleAskCommand(commandOptions, interaction, env);
    } else if (commandName === 'compare') {
      return handleCompareCommand(commandOptions, interaction, env);
    } else {
      return {
        type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        data: {
          content: `Unknown command: ${commandName}`,
          flags: 64,
        },
      };
    }
  } catch (error) {
    console.error('Slash command error:', error);
    return {
      type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
      data: {
        content: `Command failed: ${error.message}`,
        flags: 64,
      },
    };
  }
}

/**
 * Handle button click interactions
 */
async function handleButtonClick(interaction, env) {
  try {
    const customId = interaction.data?.custom_id || '';

    console.log(`Button clicked: ${customId}`);

    // Route admin button interactions
    if (customId.startsWith('admin_')) {
      return handleAdminButtonClick(interaction, env);
    }

    // Handle chart timeframe buttons (chart_{ticker}_{timeframe})
    if (customId.startsWith('chart_')) {
      return handleChartButtonClick(interaction, env);
    }

    // Unknown button
    console.warn(`Unknown button custom_id: ${customId}`);
    return {
      type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
      data: {
        content: 'Unknown button action',
        flags: 64,
      },
    };
  } catch (error) {
    console.error('Button click error:', error);
    return {
      type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
      data: {
        content: `An error occurred: ${error.message}`,
        flags: 64,
      },
    };
  }
}

/**
 * Handle chart timeframe button clicks by proxying to Python bot
 */
async function handleChartButtonClick(interaction, env) {
  try {
    const customId = interaction.data.custom_id;

    // Parse custom_id: chart_{ticker}_{timeframe}
    const parts = customId.split('_');
    if (parts.length !== 3) {
      return {
        type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        data: {
          content: 'Invalid button format',
          flags: 64,
        },
      };
    }

    const [, ticker, timeframe] = parts;

    console.log(`Chart switch: ${ticker} -> ${timeframe}`);

    // Check if Python bot URL is configured
    const botUrl = env.PYTHON_BOT_URL;

    if (!botUrl) {
      console.warn('PYTHON_BOT_URL not configured, returning acknowledgment');
      return {
        type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        data: {
          content: `📊 Chart timeframe switched to **${timeframe}** for ${ticker}!\n\n(Python bot not connected yet - configure PYTHON_BOT_URL)`,
          flags: 64,
        },
      };
    }

    // Proxy interaction to Python bot
    console.log(`Proxying to Python bot: ${botUrl}/interactions`);

    const response = await fetch(`${botUrl}/interactions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Forwarded-For': interaction.member?.user?.id || 'unknown',
      },
      body: JSON.stringify(interaction),
      signal: AbortSignal.timeout(10000), // 10 second timeout
    });

    if (!response.ok) {
      console.error(`Python bot error: ${response.status} ${response.statusText}`);
      return {
        type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        data: {
          content: `❌ Failed to generate chart (bot returned ${response.status})`,
          flags: 64,
        },
      };
    }

    // Return the Python bot's response
    const botResponse = await response.json();
    console.log(`Python bot responded with type ${botResponse.type}`);
    return botResponse;

  } catch (error) {
    console.error('Chart button error:', error);
    return {
      type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
      data: {
        content: `Failed to update chart: ${error.message}`,
        flags: 64,
      },
    };
  }
}

/**
 * Handle admin command
 */
async function handleAdminCommand(subcommand, options, interaction, env) {
  // Placeholder - implement based on slash_commands.py
  return {
    type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
    data: {
      content: `Admin command: ${subcommand}. Full implementation pending.`,
      flags: 64,
    },
  };
}

/**
 * Handle admin button clicks
 */
async function handleAdminButtonClick(interaction, env) {
  // Placeholder - implement based on admin_interactions.py
  return {
    type: InteractionResponseType.DEFERRED_UPDATE_MESSAGE,
  };
}

/**
 * Handle /check command
 */
async function handleCheckCommand(options, interaction, env) {
  // Placeholder - implement based on slash_commands.py
  return {
    type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
    data: {
      content: 'Check command. Full implementation pending.',
      flags: 64,
    },
  };
}

/**
 * Handle /research command
 */
async function handleResearchCommand(options, interaction, env) {
  // Placeholder - implement based on slash_commands.py
  return {
    type: InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
  };
}

/**
 * Handle /ask command
 */
async function handleAskCommand(options, interaction, env) {
  // Placeholder - implement based on slash_commands.py
  return {
    type: InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
  };
}

/**
 * Handle /compare command
 */
async function handleCompareCommand(options, interaction, env) {
  // Placeholder - implement based on slash_commands.py
  return {
    type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
    data: {
      content: 'Compare command. Full implementation pending.',
      flags: 64,
    },
  };
}

/**
 * Helper: Convert hex string to Uint8Array
 */
function hexToUint8Array(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes;
}

/**
 * Helper: Create JSON response
 */
function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}
