from d_rats.sessions import base, file

class BaseFormTransferSession(object):
    pass

class FormTransferSession(BaseFormTransferSession, file.FileTransferSession):
    type = base.T_FORMXFER

class PipelinedFormTransfer(BaseFormTransferSession, file.PipelinedFileTransfer):
    type = base.T_PFORMXFER

