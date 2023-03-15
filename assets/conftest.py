def pytest_itemcollected(item):
    par = item.parent.obj
    node = item.obj
    pref = ""
    suf = node.__doc__.strip() if node.__doc__ else node.__name__
    if pref and suf:
        item._nodeid = ' '.join((pref, suf))

    if suf:
        item._nodeid = suf
