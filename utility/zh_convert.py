"""t210u: 生成提示词送出前统一转简体（繁体有时处理不好）。只转送出去的文字，不改存档 / 界面。"""
import logging

_conv = None
_warned = False


def _converter():
    global _conv
    if _conv is None:
        try:
            import zhconv
            _conv = lambda s: zhconv.convert(s, "zh-cn")
        except Exception:
            try:
                import opencc
                _cc = opencc.OpenCC("t2s")
                _conv = _cc.convert
            except Exception:
                _conv = False
    return _conv


def to_simplified(text):
    """繁 → 简；不是字符串或没有库时原样返回（只警告一次）。"""
    global _warned
    if not isinstance(text, str) or not text:
        return text
    c = _converter()
    if not c:
        if not _warned:
            logging.warning("zh_convert: zhconv / opencc 都没装，提示词不转简体")
            _warned = True
        return text
    try:
        return c(text)
    except Exception as e:
        logging.warning("zh_convert: 转简体失败 %s", e)
        return text
