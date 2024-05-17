class ResetException(Exception):
    def __init__(self, message=None):
        self.message = message
        super().__init__(message)

    def __str__(self):
        if self.message:
            return f'ResetException: {self.message}'
        else:
            return 'ResetException raised'
