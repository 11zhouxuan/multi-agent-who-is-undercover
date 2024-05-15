import os
import logging

is_running_in_lambda = 'AWS_LAMBDA_FUNCTION_NAME' in os.environ
current_dir = os.getcwd()


class CustomFormatter(logging.Formatter):
    def format(self, record):
        if is_running_in_lambda:
            record.msg = str(record.msg).replace("\n", "\r")
        relative_path = os.path.relpath(record.pathname, current_dir)
        record.relativePathName = relative_path
        return super().format(record)
