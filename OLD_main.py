from io_link_funcs import *

# power analyzer constants
xitron_ip='192.168.99.245'
xitron_port='10733'


# user input
test_name=input("Enter name for test: ")
test_duration=int(input("Enter test duration in seconds: "))
polling_periods={'power':0.25,'water':5.0,'ambient':60.0}

num_samples=int(test_duration/polling_periods['power']) 
num_harms=15

# port info lists
table_names=["Cold Temp.","Hot Temp.","Cold Pres.","Hot Pres.","Cold Usage","Hot Usage","Near Ambi Temp.","Far Ambi Temp.","Near Ambi RH","Far Ambi RH"]
get_water_unit_functions=[get_cold_temp_unit,get_hot_temp_unit,get_cold_pres_unit,get_hot_pres_unit,get_cold_usage_unit,get_hot_usage_unit]

get_water_value_functions=[get_cold_temp_value,get_hot_temp_value,get_cold_pres_value,get_hot_pres_value,get_cold_usage_value,get_hot_usage_value]
column_headers='sample_num,epoch_timestamp_ms,human_timestamp,'


# compute output file names
file_ts=str(int(time.time()*1000))
ambient_log_file_name=test_name+"_ambient_"+file_ts+".csv"
water_log_file_name=test_name+"_water_"+file_ts+".csv"
power_log_file_name=test_name+"_power_"+file_ts+".csv"

# get power analyzer query string with harmonics
xitron_q_string=""
with open('ch1_q_string.txt') as query_file:
    xitron_q_string=query_file.readline()
for x in range(num_harms):
    xitron_q_string+=f',V:CH1:H{x+1},A:CH1:H{x+1}'
xitron_q_string+='\n'

# prep power analyzer for logging
xitron_socket=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
xitron_socket.connect((xitron_ip,int(xitron_port)))
xitron_socket.settimeout(1)


# create log file for ambient data and add headers
with open(ambient_log_file_name,'w') as log_file:
    log_file.write('sample_num,epoch_timestamp_ms,human_timestamp,')
    log_file.write(f'{table_names[6]} (°C),')
    log_file.write(f'{table_names[7]} (°C),')
    log_file.write(f'{table_names[8]} (% R.H.),')
    log_file.write(f'{table_names[9]} (% R.H.),')
    log_file.write('\n')

# create log file for water data and add headers
with open(water_log_file_name,'w') as log_file:
    log_file.write('sample_num,epoch_timestamp_ms,human_timestamp,')
    for port_num in range(6):
        requested_unit=get_water_unit_functions[port_num]()
        if requested_unit=='offline':
            requested_unit='???'
        log_file.write(f'{table_names[port_num]} ({requested_unit}),')
        time.sleep(0.1)

# create log file for power data and add headers
with open(power_log_file_name,'w') as log_file:
    log_file.write('sample_num,epoch_timestamp_ms,human_timestamp,')
    log_file.write(xitron_q_string.removeprefix('READ?,').rstrip('\r\n'))
    log_file.write('\n')

for sample_num in range(num_samples):
    # print out for status
    print(f'Collecting sample {sample_num} / {num_samples}',flush=True)

    # collect timestamp info
    sample_time=time.time()
    timestamp_data=make_timestamp(sample_num)
    requested_values=[]

    # collect data from power analyzer
    xitron_socket.sendall(xitron_q_string.encode())
    response_string=xitron_socket.recv(4096).decode().rstrip('\r\n')

    with open(power_log_file_name,'a') as log_file:
        log_file.write(f" {timestamp_data['sample_num']} , {timestamp_data['epoch_timestamp_ms']} , {timestamp_data['human_timestamp']},")
        log_file.write(response_string)
        log_file.write('\n')

    # wait till next poll period to log next data point
    end_time = time.time()
    elapsed = end_time - sample_time

    if elapsed > polling_periods['power']:
        print(
            f"warning: logging too slow: {elapsed:.3f} seconds to log this point",
            flush=True
        )
    else:
        time.sleep(polling_periods['power'] - elapsed)