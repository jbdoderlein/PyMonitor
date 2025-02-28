import monitoringpy
monitoringpy.init_monitoring()

@monitoringpy.pymonitor
def linear_function(x):
    a = 0
    for i in range(x*10000):
        a += i
    return a

if __name__ == "__main__":
    linear_function(10)
    linear_function(100)
    linear_function(1000)