export const connectRCMWebSocket = (onMessage: (data:any)=>void) => {

  const socket = new WebSocket("ws://127.0.0.1:8000/run-rcm/ws/rcm")

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data)
    onMessage(data)
  }

  return socket
}