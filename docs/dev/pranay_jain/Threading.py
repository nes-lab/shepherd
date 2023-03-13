import threading
import time
import random

#writing and reading pointers 
writing_ts_py = 0
reading_ts_pru = 0

#access to the buffer
access = "PY_W"

#list of data supervised by the supervisor thread
data_written = []
data_processed = []
data_read = []


class RingBuffer:
    def __init__(self, capacity):
        self.buffer = [None] * capacity
        self.capacity = capacity
        self.write_size = 0
        self.read_size = 0
        self.write_index = 0
        self.read_index = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        
    def append(self, value):
        with self.lock:
            self.buffer[self.write_index] = value
            self.write_index = (self.write_index + 1) % self.capacity
            if self.write_size < self.capacity:
                self.write_size += 1
            
            self.condition.notify_all()


    def get(self):
        with self.lock:
            value = self.buffer[self.read_index]
            self.read_index = (self.read_index+ 1) % self.capacity

            if self.read_size < self.capacity:
                self.read_size += 1

            self.condition.notify_all()
            return value
    
    def isFull(self):
        if self.write_size == self.capacity:
            self.write_size = 0
            return True
        else:
            return False
    
    def isEmpty(self):
        if self.read_size == self.capacity:
            self.read_size = 0
            return True
        else:
            return False



class write_by_python(threading.Thread):
    def __init__(self, buffer):
        threading.Thread.__init__(self)
        self.buffer = buffer

    def run(self):
        global access
        global data_written
        global writing_ts_py
        while True:
            if access == "PY_W":
                data = random.sample(range(1, 5), 2)
                writing_ts_py = self.buffer.write_index
                result = [(writing_ts_py, x) for x in data]
                self.buffer.append(result)
                data_written.append(result)
                if buffer.isFull():
                    access = "PRU_R"
                    
                
class read_by_pru(threading.Thread):
    def __init__(self, buffer):
        threading.Thread.__init__(self)
        self.buffer = buffer
        

    def run(self):
        while True:
            global access
            global reading_ts_pru
            global data_processed
            if access == "PRU_R":
                reading_ts_pru = self.buffer.read_index
                values = self.buffer.get()
                processed_result=[]
                for tuple in values:
                    processed_result.append((tuple[0], tuple[1]**2)) 

                #print(f"[PRU]: read_index = \t {reading_ts_pru} and write_index = \t {self.buffer.write_index}")
                
                self.buffer.append(processed_result)
                data_processed.append(processed_result)

                if self.buffer.isEmpty() and self.buffer.isFull():
                    access = "PY_R"
                
        


class read_by_python(threading.Thread):
    def __init__(self,buffer):
        threading.Thread.__init__(self)
        self.buffer = buffer

    def run(self):
        global access
        global data_read
        while True:
            if access == "PY_R":
                values = self.buffer.get()
                data_read.append(values)
                #print("[Reading by Python]: Data read = \t",values)
                if self.buffer.isEmpty():
                    access = "PY_W"      
                #print("[Reading by Python]: read_index = \t",self.buffer.read_index)

        
class SupervisorThread(threading.Thread):
    def __init__(self, buffer):
        threading.Thread.__init__(self)
        self.buffer = buffer
        self.every_data=[]
        
    def run(self):
        global data_written, data_processed, data_read
        while True:
            global writing_ts_py, reading_ts_pru
            if writing_ts_py < reading_ts_pru:
                print(f"SupervisorThread]Error: The reading pointer{reading_ts_pru} exceeded the writing pointer {writing_ts_py}")
                exit()

            if data_read !=  data_processed:
                if len(data_read) == len(data_processed):
                    print(f"[SupervisorThread]Error: Mismatch in data processed by PRU and data read by Python\n")
                    exit()

            

# Create the shared buffers
buffer = RingBuffer(10)

# Create the writer thread
python_write = write_by_python(buffer)
python_write.start()


# Create the reader thread
pru_read = read_by_pru(buffer)
pru_read.start()

python_read = read_by_python(buffer)
python_read.start()

# Create the supervisor thread
supervisor = SupervisorThread(buffer)
supervisor.start()

# Wait for all threads to finish
python_write.join()
pru_read.join()
python_read.join()
supervisor.join()
