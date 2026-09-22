/**
 * THE CREW — WebRTC signaling server
 *
 * Relays SDP offers/answers and ICE candidates between one broadcaster
 * (a guest's phone, going live for karaoke or a speech) and any number of
 * viewers — the dashboard (previewing/testing levels) and the projector
 * (the actual public feed) can both be connected to the same broadcaster
 * at once, so each viewer gets its own peer connection on the broadcaster
 * side, tracked by viewerId.
 *
 * This server never touches the video/audio itself — once two sides
 * connect, media flows directly between them (or via public STUN), this
 * server just introduces them.
 *
 * Rooms are keyed by event_id, so each event's broadcast is isolated.
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

// roomId (event_id) -> { broadcaster: ws|null, viewers: Map<viewerId, ws> }
const rooms = new Map();

function getRoom(roomId) {
  if (!rooms.has(roomId)) rooms.set(roomId, { broadcaster: null, viewers: new Map() });
  return rooms.get(roomId);
}

function safeSend(ws, msg) {
  if (ws && ws.readyState === ws.OPEN) ws.send(JSON.stringify(msg));
}

function cleanupSocket(ws) {
  if (!ws.roomId) return;
  const room = rooms.get(ws.roomId);
  if (!room) return;

  if (room.broadcaster === ws) {
    room.broadcaster = null;
    room.viewers.forEach(v => safeSend(v, { type: 'broadcaster-left' }));
  } else if (ws.viewerId) {
    room.viewers.delete(ws.viewerId);
    safeSend(room.broadcaster, { type: 'viewer-left', viewerId: ws.viewerId });
  }

  if (!room.broadcaster && room.viewers.size === 0) rooms.delete(ws.roomId);
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
        room.broadcaster = ws;
        room.viewers.forEach((v, viewerId) => safeSend(v, { type: 'broadcaster-joined' }));
      } else {
        ws.viewerId = crypto.randomUUID();
        room.viewers.set(ws.viewerId, ws);
        safeSend(ws, { type: room.broadcaster ? 'broadcaster-joined' : 'no-broadcaster', viewerId: ws.viewerId });
      }
      return;
    }

    const room = rooms.get(ws.roomId);
    if (!room) return;

    if (ws.role === 'broadcaster') {
      const target = room.viewers.get(msg.viewerId);
      if (target) safeSend(target, { ...msg, from: 'broadcaster' });
    } else if (room.broadcaster) {
      safeSend(room.broadcaster, { ...msg, from: 'viewer', viewerId: ws.viewerId });
    }
  });

  ws.on('close', () => cleanupSocket(ws));
  ws.on('error', () => cleanupSocket(ws));
});

server.listen(PORT, () => {
  console.log('Signaling server listening on port ' + PORT);
});
