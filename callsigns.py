import re

def find_us_callsigns(string):
    regex = '\\b[aAkKnNwW][A-z]?[0-9][A-z]{1,3}'

    return re.findall(regex, string)

def find_au_callsigns(string):
    regex = '\\b[Vv][Kk][0-9][Ff]?[A-z]{2,3}'

    return re.findall(regex, string)

callsign_functions = {
    "US" : find_us_callsigns,
    "AU" : find_au_callsigns,
}

def find_callsigns(config, string):
    list = []

    for t in callsign_functions.keys():
        if callsign_functions.has_key(t):
            print "Matching `%s' callsigns" % t
            list += callsign_functions[t](string)
    
    return list
