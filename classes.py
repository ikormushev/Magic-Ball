class AudioFile:
    def __init__(self, title, url, filesize, requested_by):
        self.title = title
        self.url = url
        self.filesize = filesize
        self.requested_by = requested_by
        self.suitable_name = self.__get_suitable_name()

    def __get_suitable_name(self):
        value = self.title

        for symbol in ('\\', '/', ':', '*', '?', '"', '<', '>', '|'):
            value = value.replace(symbol, '_')
        return value

    def __str__(self):
        return f'Title: {self.title}\nURL: {self.url}\nFile Size: {self.filesize}'
