class BigObject:
    ...
    def slow_function(...)

context = {...}

def foo(x : int, y : BigObject):
    context['counter'] += x
    y.slow_function(...)



