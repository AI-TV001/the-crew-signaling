/**
 * THE CREW — WebRTC signaling server
 *
 * Relays SDP offers/answers and ICE candidates between one broadcaster
 * (a guest's phone, going live for karaoke or a speech) and any number of
 * viewers (the projector page, and optionally the dashboard for preview).
 * It never touches the video/audio itself — once the two sides connect,
 * media flows directly between them (or via public STUN), this server
 * just introduces them.
 *
 * Rooms are keyed by event_id, so each event's broadcast is isolated.
 */

const { WebSocketServer } = require('ws');
const http = require('http');

const PORT = process.env.PORT || 8080;

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('The Crew signaling server is running.\n');
});

const wss = new WebSocketServer({ server });

// roomId (event_id) -> { broadcaster: ws|null, viewers: Set<ws> }
const rooms = new Map();

function getRoom(roomId) {
  if (!rooms.has(roomId)) rooms.set(roomId, { broadcaster: null, viewers: new Set() });
  return rooms.get(roomId);
}

function cleanupSocket(ws) {
  if (!ws.roomId) return;
  const room = rooms.get(ws.roomId);
  if (!room) return;

  if (room.broadcaster === ws) {
    room.broadcaster = null;
    room.viewers.forEach(v => safeSend(v, { type: 'broadcaster-left' }));
  } else {
    room.viewers.delete(ws);
  }

  if (!room.broadcaster && room.viewers.size === 0) rooms.delete(ws.roomId);
}

function safeSend(ws, msg) {
  if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(msg));
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
        room.viewers.forEach(v => safeSend(v, { type: 'broadcaster-joined' }));
      } else {
        room.viewers.add(ws);
        safeSend(ws, { type: room.broadcaster ? 'broadcaster-joined' : 'no-broadcaster' });
      }
      return;
    }

    const room = rooms.get(ws.roomId);
    if (!room) return;

    if (ws.role === 'broadcaster') {
      room.viewers.forEach(v => safeSend(v, { ...msg, from: 'broadcaster' }));
    } else if (room.broadcaster) {
      safeSend(room.broadcaster, { ...msg, from: 'viewer' });
    }
  });

  ws.on('close', () => cleanupSocket(ws));
  ws.on('error', () => cleanupSocket(ws));
});

server.listen(PORT, () => {
  console.log('Signaling server listening on port ' + PORT);
});

