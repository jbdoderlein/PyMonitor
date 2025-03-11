import monitoringpy




class CustomClass:
    def __init__(self, x):
        self.x = x
        self.y = 5

    def rep(self):
        return self.x + self.y
    

gcl = CustomClass(10)

@monitoringpy.pymonitor
def linear_function(x, cl):
    a = 0
    for i in range(x*10000):
        a += cl.rep()+i+gcl.rep()
    return a

if __name__ == "__main__":
    monitoringpy.init_monitoring(db_path="basic.db")
    for i in range(5):
        cl = CustomClass(i)
        linear_function(100*i, cl)