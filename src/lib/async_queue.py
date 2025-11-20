# async_queue.py
#
# This file provides an asynchronous queue implementation (AsyncQueue)
# designed for MicroPython environments, offering awaitable put and get operations.
# It mimics the behavior of asyncio.Queue but is optimized for resource-constrained devices.
#
# Author: Simon Klenk 2025
# License: MIT - See the LICENSE file in the project directory for the full license text.
import uasyncio as asyncio
from collections import deque
import sys

class AsyncQueue:
    """
    An asynchronous queue implementation similar to asyncio.Queue,
    designed for MicroPython environments.
    It supports a maximum size and provides awaitable put and get operations.
    """
    def __init__(self, maxsize=10):
        """
        Initializes the AsyncQueue.
        :param maxsize: The maximum number of items allowed in the queue.
                        If maxsize is 0, the queue size is infinite (conceptually).
                        If maxsize is > 0, the queue will block when full.
                        Must be non-negative.
        """
        if not isinstance(maxsize, int) or maxsize < 0:
            raise ValueError("maxsize must be a non-negative integer")

        self._maxsize = maxsize
        
        # Determine the internal maxlen for the collections.deque.
        # This is important for MicroPython where a truly unbounded deque might be problematic.
        if maxsize > 0:
            deque_internal_maxlen = maxsize
        elif maxsize == 0:
            deque_internal_maxlen = 20
            # Warning: Removed print statement. Logic remains, but warning is silenced.

        self._queue = deque((), deque_internal_maxlen) 
        
        # Events to signal when items are available (for get) or space is available (for put).
        self._get_event = asyncio.Event()
        self._put_event = asyncio.Event()

    async def put(self, item):
        """
        Puts an item into the queue.
        If the queue is full (and maxsize > 0), this coroutine will wait until space is available.
        :param item: The item to put into the queue.
        """
        # If maxsize is greater than 0 and the queue is full, wait for space.
        while self._maxsize > 0 and len(self._queue) >= self._maxsize:
            self._put_event.clear() # Clear the event to wait for space
            await self._put_event.wait() # Wait until an item is removed
        
        self._queue.append(item) # Add the item to the deque
        self._get_event.set() # Signal that an item is available for 'get'

    async def get(self):
        """
        Removes and returns an item from the queue.
        If the queue is empty, this coroutine will wait until an item is available.
        :return: The item removed from the queue.
        """
        # If the queue is empty, wait for an item to be put.
        while not self._queue:
            self._get_event.clear() # Clear the event to wait for an item
            await self._get_event.wait() # Wait until an item is available
        
        item = self._queue.popleft() # Remove the oldest item from the deque
        self._put_event.set() # Signal that space is available for 'put'
        return item

    def qsize(self):
        """
        Returns the number of items currently in the queue.
        :return: The current size of the queue.
        """
        return len(self._queue)

    def empty(self):
        """
        Returns True if the queue is empty, False otherwise.
        :return: True if empty, False otherwise.
        """
        return len(self._queue) == 0

    def full(self):
        """
        Returns True if the queue has maxsize items in it.
        If the queue was initialized with maxsize=0, then full() is never True.
        :return: True if full, False otherwise.
        """
        return self._maxsize > 0 and len(self._queue) >= self._maxsize