/**
 * THE CREW â€” WebRTC signaling server
 *
 * Introduces broadcasters (guests' phones) to viewers (dashboard preview,
 * projector). A room (one per event) can hold two broadcasters â€” "main"
 * and "partner" (a duet) â€” and any number of viewers. Each viewer gets its
 * own peer connection to each broadcaster, tracked by viewerId + slot.
 * Media never passes through here; only connection set-up messages do.
 */

const { WebSocketServer } = require('ws');
const http = require('http');
const crypto = require('crypto');

const PORT = process.env.PORT || 8080;

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('The Crew signaling server is running.\n');
});

const wss = new WebSocketServer({ server });

// roomId -> { broadcasters: Map<slot, ws>, viewers: Map<viewerId, ws> }
const rooms = new Map();

function getRoom(roomId) {
  if (!rooms.has(roomId)) rooms.set(roomId, { broadcasters: new Map(), viewers: new Map() });
  return rooms.get(roomId);
}

function safeSend(ws, msg) {
  if (ws && ws.readyState === ws.OPEN) ws.send(JSON.stringify(msg));
}

function cleanupSocket(ws) {
  if (!ws.roomId) return;
  const room = rooms.get(ws.roomId);
  if (!room) return;

  if (ws.role === 'broadcaster') {
    if (room.broadcasters.get(ws.slot) === ws) {
      room.broadcasters.delete(ws.slot);
      room.viewers.forEach(v => safeSend(v, { type: 'broadcaster-left', slot: ws.slot }));
    }
  } else if (ws.viewerId) {
    room.viewers.delete(ws.viewerId);
    room.broadcasters.forEach(b => safeSend(b, { type: 'viewer-left', viewerId: ws.viewerId }));
  }

  if (room.broadcasters.size === 0 && room.viewers.size === 0) rooms.delete(ws.roomId);
}

wss.on('connection', (ws) => {
  ws.on('message', (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch (e) { return; }

    if (msg.type === 'join') {
      ws.roomId = msg.room;
      ws.role = msg.role;
      const room = getRoom(msg.room);

      if (msg.role === 'broadcaster') {
        ws.slot = msg.slot === 'partner' ? 'partner' : 'main';
        room.broadcasters.set(ws.slot, ws);
        room.viewers.forEach(v => safeSend(v, { type: 'broadcaster-joined', slot: ws.slot }));
      } else {
        ws.viewerId = crypto.randomUUID();
        room.viewers.set(ws.viewerId, ws);
        if (room.broadcasters.size === 0) {
          safeSend(ws, { type: 'no-broadcaster', viewerId: ws.viewerId });
        } else {
          room.broadcasters.forEach((b, slot) => safeSend(ws, { type: 'broadcaster-joined', slot, viewerId: ws.viewerId }));
        }
      }
      return;
    }

    const room = rooms.get(ws.roomId);
    if (!room) return;

    if (ws.role === 'broadcaster') {
      const target = room.viewers.get(msg.viewerId);
      if (target) safeSend(target, { ...msg, from: 'broadcaster', slot: ws.slot });
    } else {
      const slot = msg.slot === 'partner' ? 'partner' : 'main';
      safeSend(room.broadcasters.get(slot), { ...msg, from: 'viewer', viewerId: ws.viewerId, slot });
    }
  });

  ws.on('close', () => cleanupSocket(ws));
  ws.on('error', () => cleanupSocket(ws));
});

server.listen(PORT, () => {
  console.log('Signaling server listening on port ' + PORT);
});
