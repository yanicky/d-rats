import pygtk
import gtk

class FileTransferGUI:

    def __init__(self):
        pass

    def do_send(self):
        fc = gtk.FileChooserDialog("Select file to send",
                                   None,
                                   gtk.FILE_CHOOSER_ACTION_OPEN,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        fc.run()
        print "Send file: %s" % fc.get_filename()
        fc.destroy()

    def do_recv(self):
        fc = gtk.FileChooserDialog("Receive file",
                                   None,
                                   gtk.FILE_CHOOSER_ACTION_SAVE,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        fc.run()
        print "Recv file: %s" % fc.get_filename()
        fc.destroy()
