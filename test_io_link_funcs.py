from io_link_funcs import *

reset_hot_usage()
reset_cold_usage()

print(f'hot water temp: {get_hot_temp_value()} {get_hot_temp_unit()}')
print(f'cold water temp: {get_cold_temp_value()} {get_cold_temp_unit()}')
print(f'hot water pres: {get_hot_pres_value()} {get_hot_pres_unit()}')
print(f'cold water pres: {get_cold_pres_value()} {get_cold_pres_unit()}')
print(f'hot water usage: {get_hot_usage_value()} {get_hot_usage_unit()}')
print(f'cold water usage: {get_cold_usage_value()} {get_cold_usage_unit()}')
print(f'ambient stuff: {get_all_ambient_data()}')