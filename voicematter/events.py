import socket
import json


class EventHandler:
    
    def __init__(self, path: str ):
        self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.client.connect(path)
    
    def send_event(self, action: str):
        self.client.send(
            json.dumps({
                "action": action
            }).encode()
        )
    
    def trigger(self):
        self.send_event("trigger")
    
    def pause(self):
        self.send_event("pause")
        

    
    
    
    
    
    
        