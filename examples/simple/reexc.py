import socket
import json
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("localhost", 8765))

print("Connected to reexecutionner at localhost:8765")

def send_command(socket : socket.socket, command):
    # Encode command as JSON and send
    command_json = json.dumps(command).encode() + b'\n'
    socket.sendall(command_json)
    
    # Receive and decode response
    response_data = socket.recv(40960000)
    if not response_data:
        raise ConnectionError("Connection closed by server")
        
    response_json = response_data.decode().strip()
    response = json.loads(response_json)
    return response

print(send_command(s, {"command": "set_example", "call_id": 2}))
print(send_command(s, {"command": "change"}))