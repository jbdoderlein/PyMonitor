import sys
from typing import cast
import pygame


pygame.init()

screen = pygame.display.set_mode((640, 480))

def callback_creturn(code, instruction_offset, callable, arg0):
    if callable == pygame.event.get:
        print(type(arg0), dir(arg0))
        print(arg0.__getstate__())
        print(arg0.__getitem__(0))

sys.monitoring.use_tool_id(2,"testevent")
sys.monitoring.set_events(2, sys.monitoring.events.C_RETURN | sys.monitoring.events.CALL | sys.monitoring.events.C_RAISE)
sys.monitoring.register_callback(2, sys.monitoring.events.C_RETURN, callback_creturn)

while True:
    events = pygame.event.get()
    for event in events:
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

