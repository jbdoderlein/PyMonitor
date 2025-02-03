import monitor
r = 1

class Test:
    def __init__(self):
        self.r = 1

    def useless(self):
        i = 0
        for i in range(30000000):
            i += 1
        return i
    def useless2(self, x):
        return x+1

tt1 = Test()
tt2 = Test()

def test(v, tt):
    print(v)
    print(tt1.r)
    tt.useless()
    a = tt.useless2(1)
    print(a)
    print(tt.useless2(2))
    return v

test(4, tt2)