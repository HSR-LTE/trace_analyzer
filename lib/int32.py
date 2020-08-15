import ctypes

def minus(a, b):
    val = ctypes.c_int32(a - b).value
    return val

def after(a, b):
    return minus(a, b) > 0

def before(a, b):
    return after(b, a)
