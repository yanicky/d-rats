import os
import subprocess

class Spelling:
    def __open_aspell(self):
        kwargs = {}
        if subprocess.mswindows:
            su = subprocess.STARTUPINFO()
            su.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            su.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = su

        p = subprocess.Popen([self.__aspell, "pipe"],
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             **kwargs)
        return p

    def __close_aspell(self):
        if self.__pipe:
            self.__pipe.terminate()
            self.__pipe = None

    def __init__(self, aspell="aspell", persist=True):
        self.__aspell = aspell
        self.__persist = persist
        self.__pipe = None

    def lookup_word(self, wiq):
        for c in wiq:
            c = ord(c)
            if c < ord('A') or c > ord('z') or \
                    (c > ord('Z') and c < ord('a')):
                return []

        try:
            self.__pipe.stdout.readline()
        except Exception, e:
            print "Demand-opening aspell..."
            self.__pipe = self.__open_aspell()
            self.__pipe.stdout.readline()

        self.__pipe.stdin.write("%s%s" % (wiq, os.linesep))
        suggest_str = self.__pipe.stdout.readline()

        if not self.__persist:
            self.__close_aspell()

        if suggest_str.startswith("*"):
            return []
        elif not suggest_str.startswith("&"):
            raise Exception("Unknown response from aspell: %s" % suggest_str)

        suggestions = suggest_str.split()
        return suggestions[4:]     

    def test(self):
        try:
            s = self.lookup_word("speling")
            if s[0] != "spelling,":
                print "Unable to validate first suggestion of `spelling'"
                print s[0]
                return False
        except Exception, e:
            print "Spelling test failed: %s" % e
            return False

        print "Tested spelling okay: %s" % s
        return True
    

def test_word(spell, word):
    spell.stdin.write(word + "\n")
    result = spell.stdout.readline()
    spell.stdout.readline()

    if result.startswith("*"):
        return []
    elif result.startswith("&"):
        items = result.split()
        return items[4:]
    else:
        print "Unknown response: `%s'" % result

SPELL = None

def get_spell():
    global SPELL
    if not SPELL:
        SPELL = Spelling()
    return SPELL

if __name__ == "__main__":
    s = Spelling()
    print s.lookup_word("speling")
    print s.lookup_word("teh")
    print s.lookup_word("foo")
