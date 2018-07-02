from dxlclient.callbacks import EventCallback
from dxlclient.client import DxlClient
from dxlclient.client_config import DxlClientConfig
from dxlclient.message import Event
import time
from threading import Condition

import logging
log_formatter = logging.Formatter('%(asctime)s %(name)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.addHandler(console_handler)
logger.setLevel(logging.INFO)
logging.getLogger().setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


# Create DXL configuration from file
config = DxlClientConfig.create_dxl_config_from_file('dxlclient.config')
print "Starting the ATD/PAN FW OpenDXL integrator"
# Create the client

# The topic to listen from
EVENT_TOPIC = "/mcafee/event/atd/file/report"

# The total number of events to send
TOTAL_EVENTS = 1000

# Condition/lock used to protect changes to counter
event_count_condition = Condition()

# The events received (use an array so we can modify in callback)
event_count = [0]

# Create the client
with DxlClient(config) as client:

    print "Connecting to OpenDXL"
    # Connect to the fabric
    client.connect()

    print "Connected to OpenDXL"
    #
    # Register callback and subscribe
    #

    # Create and add event listener
    class MyEventCallback(EventCallback):
        def on_event(self, event):
            with event_count_condition:
                # Print the payload for the received event
                print("Received event: " + event.payload.decode())
                # Increment the count
                event_count[0] += 1
                # Notify that the count was increment
                event_count_condition.notify_all()

    # Register the callback with the client
    client.add_event_callback(EVENT_TOPIC, MyEventCallback())

    # Wait until all events have been received
    print("Waiting for events to be received...")
    with event_count_condition:
        while event_count[0] < TOTAL_EVENTS:
            event_count_condition.wait()

    # Print the elapsed time
    print("Elapsed time (ms): " + str((time.time() - start) * 1000))