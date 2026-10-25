import hpprime

def trans(text):
    return str(text).replace('"', '""').replace("\\", 2*"\\")

def myprint(text, color):
    hpprime.eval('print2d("{}\n", 3, {})'.format(trans(text), color))

def p_log(text):
    myprint(text, 0xacacac)
    
def p_warning(text):
    myprint(text, 0xffaa22)

def p_error(text):
    myprint(text, 0xff0000)

def p_pass(text):
    myprint(text, 0x22cb23)

def p_out(text):
    myprint(text, 0x0000ff)