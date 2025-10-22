/**
 * Simple test script for the Discord Interactions Worker
 *
 * This script helps test the worker locally without needing to deploy.
 * Run with: node test-worker.js
 *
 * Note: This is a basic test harness. For production testing, use wrangler dev
 * and Cloudflare Tunnel to test with actual Discord requests.
 */

const crypto = require('crypto');

// Test PING interaction
const testPing = {
  type: 1, // PING
};

// Test button click interaction
const testButtonClick = {
  type: 3, // MESSAGE_COMPONENT
  data: {
    custom_id: 'chart_AAPL_1M',
  },
  message: {
    id: '1234567890',
    embeds: [
      {
        title: 'AAPL Chart',
        image: {
          url: 'attachment://chart_AAPL_1D.png',
        },
      },
    ],
  },
  channel_id: '1234567890',
};

// Test slash command interaction
const testSlashCommand = {
  type: 2, // APPLICATION_COMMAND
  data: {
    name: 'check',
    options: [
      {
        name: 'ticker',
        type: 3, // STRING
        value: 'AAPL',
      },
    ],
  },
};

console.log('='.repeat(60));
console.log('Discord Interactions Worker - Test Suite');
console.log('='.repeat(60));
console.log('');

console.log('Test 1: PING Interaction');
console.log('Expected response: {"type":1}');
console.log('Payload:', JSON.stringify(testPing, null, 2));
console.log('');

console.log('Test 2: Button Click Interaction');
console.log('Expected response: {"type":6} (deferred update)');
console.log('Payload:', JSON.stringify(testButtonClick, null, 2));
console.log('');

console.log('Test 3: Slash Command Interaction');
console.log('Expected response: Command-specific response');
console.log('Payload:', JSON.stringify(testSlashCommand, null, 2));
console.log('');

console.log('='.repeat(60));
console.log('To test with actual Discord requests:');
console.log('');
console.log('1. Run: npm run dev');
console.log('   (Starts local dev server on http://localhost:8787)');
console.log('');
console.log('2. In another terminal, run Cloudflare Tunnel:');
console.log('   cloudflared tunnel --url http://localhost:8787');
console.log('');
console.log('3. Set the tunnel URL in Discord Developer Portal:');
console.log('   Interactions Endpoint URL: https://<tunnel>.trycloudflare.com/interactions');
console.log('');
console.log('4. Monitor logs:');
console.log('   npm run tail');
console.log('');
console.log('='.repeat(60));
console.log('');

console.log('Sample curl commands for testing:');
console.log('');
console.log('Health check:');
console.log('  curl http://localhost:8787/health');
console.log('');
console.log('Root page:');
console.log('  curl http://localhost:8787/');
console.log('');
console.log('Note: Testing /interactions requires Discord signature verification.');
console.log('Use wrangler dev + Cloudflare Tunnel for full integration testing.');
console.log('');
