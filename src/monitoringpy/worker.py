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
        retry_delay = 0.5  # Initial retry delay
        max_retry_delay = 5.0  # Maximum retry delay
        
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
                if (buffer and current_time - last_flush_time >= self.flush_interval) or len(buffer) >= 25:
                    # Get a sample of function names for logging
                    function_names = [item.get('function', 'unknown') for item in buffer[:3]]
                    if len(buffer) > 3:
                        function_names.append(f"... and {len(buffer) - 3} more")
                    
                    logger.debug(f"Flushing buffer with {len(buffer)} items: {', '.join(function_names)}")
                    
                    # Try to save with retries
                    retry_count = 0
                    max_retries = 3
                    while retry_count < max_retries:
                        save_result = self.db_manager.save_to_database(buffer)
                        if save_result:
                            buffer.clear()
                            last_flush_time = current_time
                            # Reset error count and retry delay on successful save
                            self.error_count = 0
                            retry_delay = 0.5
                            break
                        else:
                            retry_count += 1
                            if retry_count < max_retries:
                                logger.warning(f"Retry {retry_count}/{max_retries} after failed save")
                                time.sleep(retry_delay)
                                retry_delay = min(retry_delay * 2, max_retry_delay)
                    
                    if retry_count == max_retries:
                        # If all retries failed
                        self.error_count += 1
                        if self.error_count <= self.max_consecutive_errors or self.error_count % 100 == 0:
                            logger.error(f"Failed to save to database after {max_retries} retries (error #{self.error_count}) - Buffer size: {len(buffer)}")
                            # Log a sample of the data that failed to save
                            if buffer:
                                sample = buffer[0]
                                logger.error(f"Sample data: Function: {sample.get('function', 'unknown')}, File: {sample.get('file', 'unknown')}")
                        
                        # If we've had too many errors, clear the buffer to avoid memory issues
                        if self.error_count > 10:
                            logger.warning(f"Clearing buffer after {self.error_count} consecutive errors - Buffer size: {len(buffer)}")
                            buffer.clear()
                            last_flush_time = current_time
            except Exception as e:
                self.error_count += 1
                if self.error_count <= self.max_consecutive_errors or self.error_count % 100 == 0:
                    logger.error(f"Error in log worker (error #{self.error_count}): {e}")
                    logger.error(traceback.format_exc())
                    if buffer:
                        logger.error(f"Buffer size: {len(buffer)}")
                        sample = buffer[0]
                        logger.error(f"Sample data: Function: {sample.get('function', 'unknown')}, File: {sample.get('file', 'unknown')}")
                
                # Sleep with exponential backoff
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
                
                # If we've had too many errors, clear the buffer to avoid memory issues
                if self.error_count > 10 and buffer:
                    logger.warning(f"Clearing buffer after {self.error_count} consecutive errors - Buffer size: {len(buffer)}")
                    buffer.clear()
                    last_flush_time = time.time()
        
        # Final flush on shutdown
        if buffer:
            try:
                logger.info(f"Final flush of {len(buffer)} items on shutdown")
                retry_count = 0
                max_retries = 3
                while retry_count < max_retries:
                    if self.db_manager.save_to_database(buffer):
                        logger.info("Final flush completed successfully")
                        break
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"Retry {retry_count}/{max_retries} for final flush")
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, max_retry_delay)
                
                if retry_count == max_retries:
                    logger.error("Failed to complete final flush after all retries")
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
        logger.info("Starting shutdown process")
        self.shutdown_flag.set()
        
        try:
            if self.worker_thread.is_alive():
                logger.info("Worker thread is still alive, waiting for it to finish")
                logger.info(f"Current queue size: {self.log_queue.qsize()}")
                
                self.worker_thread.join(timeout=10.0)  # Increased from 5.0 to 10.0 seconds
                
                if self.worker_thread.is_alive():
                    logger.warning("Worker thread did not finish in time")
                    logger.warning(f"Queue size: {self.log_queue.qsize()}")
                    logger.warning("Stack trace of worker thread:")
                    logger.warning(traceback.format_stack())
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
                logger.info(f"Found {len(remaining_items)} remaining items to flush")
                try:
                    logger.info("Attempting to save remaining items")
                    self.db_manager.save_to_database(remaining_items)
                    logger.info("Successfully saved remaining items")
                except Exception as e:
                    logger.error(f"Error during final flush of remaining items: {e}")
                    logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"Error during worker shutdown: {e}")
            logger.error(traceback.format_exc()) 