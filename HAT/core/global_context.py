class GlobalContext:
    _dit = {}
    def set_context(self, key, value):
        self._dit[key] = value
    def set_by_dict(self, dic):
        self._dit.update(dic)
    def get_context(self, key):
        return self._dit.get(key, None)
    def show_context(self):
        return self._dit
