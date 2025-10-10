import pygame
import io
import pickle
import copyreg
from spacetimepy import init_monitoring, pymonitor
from spacetimepy.core.representation import PickleConfig

# Define a custom reducer for pygame events
def reduce_pygame_event(e):
    """Custom reducer for pygame event objects"""
    return (pygame.event.Event, (e.type, e.dict.copy()))

# Initialize pygame
pygame.init()

# Create a custom pickle config with the pygame event reducer
def get_custom_pickle_config():
    dispatch_table = copyreg.dispatch_table.copy()
    dispatch_table[pygame.event.EventType] = reduce_pygame_event
    return PickleConfig(dispatch_table=dispatch_table)

# Initialize monitoring with custom pickle config
pickle_config = get_custom_pickle_config()
monitor = init_monitoring(db_path="pygame_events.db", pickle_config=pickle_config)

@pymonitor
def process_event(event):
    """Process a pygame event"""
    print(f"Processing event: {event}")
    if event.type == pygame.KEYDOWN:
        print(f"Key pressed: {pygame.key.name(event.key)}")
    elif event.type == pygame.MOUSEBUTTONDOWN:
        print(f"Mouse button {event.button} pressed at {event.pos}")
    return event

@pymonitor
def main():
    """Main function to demonstrate custom pickling of pygame events"""
    # Create a small display
    screen = pygame.display.set_mode((320, 240))
    pygame.display.set_caption("SpaceTimePy Custom Pickle Example")
    
    # Create some events to monitor
    space_event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, unicode=" ")
    mouse_event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(100, 100), button=1)
    
    # Process the events through our monitored function
    result1 = process_event(space_event)
    result2 = process_event(mouse_event)
    
    # The events should be correctly pickled and stored in the database
    print("\nAll events processed. The events were pickled using custom reducers.")
    print("You can explore the database to see that pygame events were stored correctly.")
    
    # Manual verification of custom pickling (not using the monitoring system)
    print("\nVerification of custom pickling:")
    dispatch_table = get_custom_pickle_config().dispatch_table
    
    f = io.BytesIO()
    p = pickle.Pickler(f)
    p.dispatch_table = dispatch_table
    p.dump(space_event)
    
    # Read it back
    f.seek(0)
    loaded = pickle.Unpickler(f).load()
    
    print(f"Original event: {space_event}")
    print(f"Unpickled event: {loaded}")
    print(f"Same type: {type(loaded) == type(space_event)}")
    
    # Clean up
    pygame.quit()
    return "Done"

if __name__ == "__main__":
    # Run the example
    try:
        result = main()
        print(f"Result: {result}")
    finally:
        # Cleanup can be done here
        pygame.quit() 