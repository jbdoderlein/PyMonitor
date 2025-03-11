import threading
import queue
import time
import logging
import traceback

# Configure logging
logger = logging.getLogger(__name__)

class LogWorker:
    """
    Worker thread that processes log entries from a queue and saves them to the database.
    """
    
    def __init__(self, db_manager, queue_size=1000, flush_interval=1.0):
        """
        Initialize the log worker.
        
        Args:
            db_manager: DatabaseManager instance
            queue_size: Maximum size of the queue
            flush_interval: How often to flush the queue (in seconds)
        """
        self.db_manager = db_manager
        self.log_queue = queue.Queue(maxsize=queue_size)
        self.flush_interval = flush_interval
        self.worker_thread = threading.Thread(target=self._log_worker, daemon=True)
        self.shutdown_flag = threading.Event()
        self.error_count = 0
        self.max_consecutive_errors = 5  # After this many errors, we'll log at a reduced rate
    
    def start(self):
        """Start the worker thread"""
        try:
            self.worker_thread.start()
            logger.info("Log worker thread started")
        except Exception as e:
            logger.error(f"Failed to start log worker thread: {e}")
            logger.error(traceback.format_exc())
    
    def _log_worker(self):
        """Background thread that processes log entries from the queue"""
        buffer = []
        last_flush_time = time.time()
        
        while not self.shutdown_flag.is_set():
            try:
                # Get items from the queue with a timeout to allow checking the shutdown flag
                try:
                    trace_data = self.log_queue.get(timeout=0.1)
                    buffer.append(trace_data)
                    self.log_queue.task_done()
                except queue.Empty:
                    pass
                
                current_time = time.time()
                # Flush the buffer if it's been too long or if we have enough items
                if (buffer and current_time - last_flush_time >= self.flush_interval) or len(buffer) >= 100:
                    if self.db_manager.save_to_database(buffer):
                        buffer.clear()
                        last_flush_time = current_time
                        # Reset error count on successful save
                        if self.error_count > 0:
                            logger.info("Database operations resumed successfully after errors")
                            self.error_count = 0
                    else:
                        # If save failed but didn't raise an exception, log it
                        self.error_count += 1
                        if self.error_count <= self.max_consecutive_errors or self.error_count % 100 == 0:
                            logger.error(f"Failed to save to database (error #{self.error_count})")
                        
                        # If we've had too many errors, clear the buffer to avoid memory issues
                        if self.error_count > 10:
                            logger.warning(f"Clearing buffer after {self.error_count} consecutive errors")
                            buffer.clear()
                            last_flush_time = current_time
            except Exception as e:
                self.error_count += 1
                if self.error_count <= self.max_consecutive_errors or self.error_count % 100 == 0:
                    logger.error(f"Error in log worker (error #{self.error_count}): {e}")
                    logger.error(traceback.format_exc())
                
                # Sleep briefly to avoid tight error loops
                time.sleep(0.5)
                
                # If we've had too many errors, clear the buffer to avoid memory issues
                if self.error_count > 10 and buffer:
                    logger.warning(f"Clearing buffer after {self.error_count} consecutive errors")
                    buffer.clear()
                    last_flush_time = time.time()
        
        # Final flush on shutdown
        if buffer:
            try:
                logger.info(f"Final flush of {len(buffer)} items on shutdown")
                self.db_manager.save_to_database(buffer)
            except Exception as e:
                logger.error(f"Error during final flush: {e}")
    
    def add_to_queue(self, data):
        """
        Add data to the queue for processing.
        
        Args:
            data: Data to add to the queue
            
        Returns:
            bool: True if added to queue, False if queue is full
        """
        try:
            self.log_queue.put_nowait(data)
            return True
        except queue.Full:
            return False
        except Exception as e:
            logger.error(f"Error adding to queue: {e}")
            return False
    
    def shutdown(self):
        """Gracefully shut down the logging thread"""
        logger.info("Shutting down log worker")
        self.shutdown_flag.set()
        
        try:
            if self.worker_thread.is_alive():
                logger.info("Waiting for worker thread to finish")
                self.worker_thread.join(timeout=5.0)  # Wait up to 5 seconds for the thread to finish
                
                if self.worker_thread.is_alive():
                    logger.warning("Worker thread did not finish in time")
                else:
                    logger.info("Worker thread finished successfully")
                
            # If there are still items in the queue, flush them directly
            remaining_items = []
            while not self.log_queue.empty():
                try:
                    remaining_items.append(self.log_queue.get_nowait())
                    self.log_queue.task_done()
                except queue.Empty:
                    break
                    
            if remaining_items:
                logger.info(f"Flushing {len(remaining_items)} remaining items")
                try:
                    self.db_manager.save_to_database(remaining_items)
                    logger.info("Final flush completed successfully")
                except Exception as e:
                    logger.error(f"Error during final flush of remaining items: {e}")
        except Exception as e:
            logger.error(f"Error during worker shutdown: {e}")
            logger.error(traceback.format_exc()) 