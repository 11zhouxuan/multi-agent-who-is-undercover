class _Const(object):
    class ConstError(TypeError):
        def __init__(self, msg):
            super().__init__(msg)

    def __setattr__(self, name, value):
        if name in self.__dict__:
            err = self.ConstError("Can't change const.%s" % name)
            raise err
        if not name.isupper():
            err = self.ConstError('Const name "%s" is not all uppercase' % name)
            raise err
        self.__dict__[name] = value


const = _Const()

const.LOGGER_API = "api"
const.CHINAWARE_WORDS_LIST = [
        {
            "undercover_word": "白瓷",
            "common_word": "青花瓷",
            "prefer_words":['器形',"图案","用途"]
        },
        {
            "undercover_word": "石膏",
            "common_word": "白瓷",
            "prefer_words":['颜色',"质地","耐腐蚀"]
        },
        {
            "undercover_word": "塑像",
            "common_word": "手办",
            "prefer_words":['题材',"工艺","价值"]
        },
        {
            "undercover_word": "电窑",
            "common_word": "柴窑",
            "prefer_words":['用途',"产出","形态结构"]
        },
        {
            "undercover_word": "玻璃",
            "common_word": "瓷器",
            "prefer_words":['质地',"重量","观感"]
        }
    ]