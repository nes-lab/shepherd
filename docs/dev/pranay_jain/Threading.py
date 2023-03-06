import threading
from threading import Thread, Event
import datetime
from time import sleep
from threading import Lock
import random

#Event to detect the end of write operation
stop_event = threading.Event()

###Variable Definition

#List of Data to be written by the host(Values taken just for a reference)
data_list_write = [1,2,3,4,5,6,7,8,9,0,9,10,11,12,13,14,15,16,0]        #To Note: 0 is treated as the end of the message   

#List of processed data to be read by the host
data_list_read = []

#List containing the start and end point of a message
end_points = [0]

#Function to write the variable and process the data{
# Parameters: 
#   host_message: data_list_write as defined above
#   iteration_value: states the number of times the information should be written(Analogous to multiple information)}

def write_variable(host_message,iteration_value):
    global write_pointer                             #To detect the end of each message
    write_pointer = 0                                

    ## Writing the same data multiple times to create a scenario of multiple messages
    for i in range(iteration_value):
                        
        for index,data in enumerate(host_message): 
            print(f"\n [Writing Thread]: Message from the host is: {data} at time {datetime.datetime.now()}")
            
            #Processing and storing the data{
            # Squaring the data just as an example of data processing}
            data_list_read.append(data**2)

            #Checking the end point of a message
            if data == 0:
                write_pointer = write_pointer +1              #Detects the end point of the latest information
                end_points.append(len(data_list_read))         #Storing the end point of each information
                                
    #Setting up the stop event to close the read operation                             
    sleep(1)
    stop_event.set()
    print('\n Writing Stopped')

#Function to read the processed data to the host
def read_variable():
    read_pointer = 0              #Local variable to keep track with the latest index in order to trigger read pointer
    while True:
        while read_pointer < write_pointer:    #Condition to trigger reading operation
            
            #updating temp_index to latest_index in order to avoid multiple reads
            read_pointer = write_pointer       

            #Checking if start and end point is detected before printing the information
            while len(end_points)>1:
                read_data = data_list_read[end_points[0]:end_points[1]]
                print(f"\n [Reading Thread]: Message to the host is: {read_data} at time {datetime.datetime.now()}")
                
                #Popping out the starting point of each information 
                #The end point of each message would be the start point of the next message
                
                end_points.pop(0)   

        #Waiting for writing function to inform the end of communication   
        if stop_event.is_set():
            break
    print('\n Reading Stopped')


#Defining two threads{
# t_write for writing and t_read for reading the data}

t_write = Thread(target=write_variable, args=(data_list_write, 2))
t_read = Thread(target=read_variable, args=())

#Starting both the threads
t_write.start()
t_read.start()

#Joining both the threads
t_write.join()
t_read.join()





