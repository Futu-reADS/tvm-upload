import time
from pathlib import Path
import tempfile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DebugHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        print(f"EVENT: {event.event_type} - {event.src_path}")

# Create temp directory
temp_dir = Path(tempfile.mkdtemp())
print(f"Monitoring: {temp_dir}")

# Start observer
observer = Observer()
handler = DebugHandler()
observer.schedule(handler, str(temp_dir), recursive=False)
observer.start()

time.sleep(0.5)

# Create file
test_file = temp_dir / "test.log"
print(f"\nCreating file: {test_file}")
test_file.write_text("data")

# Wait and see events
time.sleep(2)

observer.stop()
observer.join()

# Cleanup
import shutil
shutil.rmtree(temp_dir)
