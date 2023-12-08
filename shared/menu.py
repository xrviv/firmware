# (c) Copyright 2018 by Coinkite Inc. This file is covered by license found in COPYING-CC.
#
# menu.py - Implement an interactive menu system.
#
import gc
from ux import PressRelease, the_ux
from uasyncio import sleep_ms
from charcodes import (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_HOME, KEY_SPACE,
                        KEY_END, KEY_PAGE_UP, KEY_PAGE_DOWN, KEY_ENTER, KEY_CANCEL)
from version import has_qwerty

# Number of full text lines per screen.
# - we will draw one past this because on Mk1-4 it shows a partial line under those 4
if not has_qwerty:
    PER_M = 4
else:
    from lcd_display import CHARS_H
    PER_M = CHARS_H - 1

# do wrap-around, but only for mega menus like seed words
WRAP_IF_OVER = const(16)

def numpad_remap(key):
    # map from numpad+2 (12 keys) into symbolic names
    # - might only make sense within context of menus.
    if key == '5':
        return KEY_UP
    elif key == '8':
        return KEY_DOWN
    elif key == '7':
        return KEY_PAGE_UP
    elif key == '9':
        return KEY_END
    elif key == '0':
        return KEY_HOME
    elif key == 'y':
        return KEY_ENTER
    elif key == 'x':
        return KEY_CANCEL
    else:
        # keys 1-4 useful for selecting the top visible items from menu
        return key

def start_chooser(chooser):
    # get which one to show as selected, list of choices, and fcn to call after
    # - optional: a function to preview a value
    selected, choices, setter, *preview = chooser()

    if preview:
        preview, = preview

    async def picked(menu, picked, xx_self):
        menu.chosen = picked
        menu.show()
        await sleep_ms(100)     # visual feedback that we changed it
        setter(picked, choices[picked])

        the_ux.pop()

    # make a new menu, just for the choices
    m = MenuSystem([MenuItem(c, f=picked) for c in choices], chosen=selected)
    if preview:
        m.late_draw = lambda dis: preview(m.cursor)

    the_ux.push(m)

class MenuItem:
    def __init__(self, label, menu=None, f=None, chooser=None, arg=None, predicate=None, shortcut=None):
        self.label = label
        self.arg = arg
        if menu:
            self.next_menu = menu
        if f:
            self.next_function = f
        if chooser:
            self.chooser = chooser
        if predicate:
            self.predicate = predicate
        if shortcut:
            self.shortcut_key = shortcut
    
    async def activate(self, menu, idx):

        if getattr(self, 'chooser', None):
            start_chooser(self.chooser)

        else:
            # nesting menus, and functions and so on.
            f = getattr(self, 'next_function', None)
            if f:
                rv = await f(menu, idx, self)
                if isinstance(rv, MenuSystem):
                    # XXX the function should do this itself
                    # go to new menu
                    the_ux.replace(rv)

            m = getattr(self, 'next_menu', None)

            if callable(m):
                m = await m(menu, idx, self)

            if isinstance(m, list):
                m = MenuSystem(m)

            if m:
                the_ux.push(m)

class NonDefaultMenuItem(MenuItem):
    # Show a checkmark if setting is defined and not the default ... so know know it's set
    def __init__(self, label, nvkey, prelogin=False, default_value=None, **kws):
        super().__init__(label, **kws)
        self.nvkey = nvkey
        self.prelogin = prelogin
        self.def_value = default_value       # treated the same as missing

    def is_chosen(self):
        # should we show a check in parent menu?
        if self.prelogin:
            from nvstore import SettingsObject
            s = SettingsObject.prelogin()
        else:
            from glob import settings
            s = settings

        return bool(s.get(self.nvkey, self.def_value))


class ToggleMenuItem(MenuItem):
    # Handle toggles: must use undefined (missing) as default
    # - can remap values a little, but default is to store 0/1/2
    def __init__(self, label, nvkey, choices, predicate=None, story=None, on_change=None, invert=False, value_map=None):
        self.label = label
        self.story = story
        self.nvkey = nvkey
        self.choices = choices          # list of strings, at least 2
        self.on_change = on_change      # optional, since some are just settings
        if invert:
            self.invert = True
        if value_map:
            self.value_map = value_map
        if predicate:
            self.predicate = predicate

    def is_chosen(self):
        # should we show a check in parent menu?
        from glob import settings
        if self.nvkey == "chain":
            rv = True if settings.get(self.nvkey) in ["XRT", "XTN"] else False
        else:
            rv = bool(settings.get(self.nvkey, 0))
        if getattr(self, 'invert', False):
            rv = not rv
        return rv
    
    async def activate(self, menu, idx):
        from glob import settings
        from ux import ux_show_story

        # skip story if default value has been changed
        if self.nvkey == "chain":
            default = settings.get(self.nvkey) == "BTC"
        else:
            default = settings.get(self.nvkey, None) == None
        if self.story and default:
            ch = await ux_show_story(self.story)
            if ch == 'x': return

        value = settings.get(self.nvkey, 0)
        if hasattr(self, 'value_map'):
            for n,v in enumerate(self.value_map):
                if value == v:
                    value = n
                    break
            else:
                value = 0           # robustness

        m = MenuSystem([MenuItem(c, f=self.picked) for c in self.choices], chosen=value)
        the_ux.push(m)

    async def picked(self, menu, picked, xx_self):
        from glob import settings

        menu.chosen = picked
        menu.show()
        await sleep_ms(100)     # visual feedback that we changed it

        if picked == 0:
            settings.remove_key(self.nvkey)
        else:
            if hasattr(self, 'value_map'):
                picked = self.value_map[picked]     # want IndexError if wrong here
            settings.set(self.nvkey, picked)

        if self.on_change:
            await self.on_change(picked)

        the_ux.pop()


class MenuSystem:

    def __init__(self, menu_items, chosen=None, should_cont=None, space_indicators=False):
        self.should_continue = should_cont or (lambda: True)
        self.replace_items(menu_items)
        self.space_indicators = space_indicators
        self.chosen = chosen
        if chosen is not None:
            self.goto_idx(chosen)

    # subclasses: override us
    #
    def late_draw(self, dis):
        pass

    def update_contents(self):
        # something changed in system state; maybe re-construct menu contents
        pass

    def replace_items(self, menu_items, keep_position=False):
        # only safe to keep position if you know number of items isn't changing
        if not keep_position:
            self.cursor = 0
            self.ypos = 0

        self.items = [m for m in menu_items if not getattr(m, 'predicate', None) or m.predicate()]
        self.count = len(self.items)

    def goto_label(self, label):
        # pick menu item based on label text
        for i, m in enumerate(self.items):
            if m.label.endswith(label):
                self.goto_idx(i)
                return True
        return False

    def show(self):
        #
        # Redraw the menu.
        #
        from glob import dis

        dis.clear()

        cursor_y = None
        for n in range(self.ypos+PER_M+1):
            if n+self.ypos >= self.count: break

            msg = self.items[n+self.ypos].label
            is_sel = (self.cursor == n+self.ypos)
            if is_sel:
                cursor_y = n

            # show check?
            checked = (self.chosen is not None and (n+self.ypos) == self.chosen)

            fcn = getattr(self.items[n+self.ypos], 'is_chosen', None)
            if fcn and fcn():
                checked = True

            dis.menu_draw(n, msg, is_sel, checked, self.space_indicators)

        # subclass hook
        self.late_draw(dis)

        if self.count > PER_M:
            dis.scroll_bar(self.ypos / (self.count-PER_M))

        dis.menu_show(cursor_y)

    def get_wrap_length(self):
        from glob import settings
        # wa is boolean value from config
        # True --> wrap around all menus with length greater than 1
        # False --> wrap around is active only for menus with length > WRAP_IF_OVER
        wrap = settings.get("wa", 0)
        return 1 if wrap else WRAP_IF_OVER

    def down(self):
        if self.cursor < self.count-1:
            self.cursor += 1

            if self.cursor - self.ypos >= (PER_M-1):
                self.ypos += 1
        else:
            wrap_length = self.get_wrap_length()
            if self.count > wrap_length:
                self.goto_idx(0)

    def up(self):
        if self.cursor > 0:
            self.cursor -= 1
            if self.cursor < self.ypos:
                self.ypos -= 1
        else:
            wrap_length = self.get_wrap_length()
            if self.count > wrap_length:
                self.goto_idx(self.count - 1)

    def top(self):
        self.cursor = 0
        self.ypos = 0

    def goto_n(self, n):
        # goto N from top of (current) screen
        # change scroll only if needed to make it visible
        self.cursor = max(min(n + self.ypos, self.count-1), 0)
        self.ypos = max(self.cursor - n, 0)

    def goto_idx(self, n):
        # skip to any item, force cusor near middle of screen
        n = self.count-1 if n >= self.count else n
        n = 0 if n < 0 else n
        self.cursor = n
        if n < PER_M-1:
            self.ypos = 0
        else:
            self.ypos = n - 2

    def page(self, n):
        # relative page dn/up - may wrap around
        if n == 1:
            for i in range(PER_M):
                self.down()
        else:
            for i in range(PER_M):
                self.up()

    # events
    def on_cancel(self):
        # override me
        if the_ux.pop():
            # top of stack (main top-level menu)
            self.top()

    async def activate(self, idx):
        # Activate a specific choice in our menu.
        #
        if idx is None:
            # "go back" or cancel or something
            self.on_cancel()
        else:
            assert idx < self.count
            ch = self.items[idx]

            await ch.activate(self, idx)


    async def interact(self):
        # Only public entry point: do stuff.
        #
        while self.should_continue() and the_ux.top_of_stack() == self:
            ch = await self.wait_choice()
            gc.collect()
            await self.activate(ch)
            
    async def wait_choice(self):
        #
        # Wait until a menu choice is picked; let them move around
        # the menu, keep redrawing it and so on.

        key = None

        # 5,8 have key-repeat, not others
        pr = PressRelease('790xy')      # TODO: q1 needs

        while 1:
            self.show()

            key = await pr.wait()

            if not key:
                continue

            if not has_qwerty:
                key = numpad_remap(key)

            if key == KEY_ENTER or key == KEY_SPACE:
                # selected - done
                return self.cursor
            elif key == KEY_CANCEL:
                # abort/nothing selected/back out?
                return None
            elif key == KEY_UP:
                self.up()
            elif key == KEY_DOWN:
                self.down()
            elif key == KEY_PAGE_UP:
                self.page(-1)
            elif key == KEY_PAGE_DOWN:
                self.page(1)
            elif key == KEY_END:
                self.goto_idx(self.count-1)
            elif key == KEY_HOME:
                # zip to top, no selection
                self.cursor = 0
                self.ypos = 0
            elif '1' <= key <= '9':
                # jump down, based on screen postion
                self.goto_n(ord(key)-ord('1'))
            else:
                # maybe a shortcut?
                for n, item in enumerate(self.items):
                    if getattr(item, 'shortcut_key', None) == key:
                        # matched. do it
                        self.goto_idx(n)
                        return self.cursor

                # search downwards for a menu item that starts with indicated letter
                # if found, select it but dont drill down
                lst = list(range(self.cursor+1, self.count)) + list(range(0, self.cursor))
                for n in lst:
                    if self.items[n].label[0].upper() == key.upper():
                        self.goto_idx(n)
                        break
                else:
                    print("Unused menu key: %s=0x%02x" % (key, ord(key)))

# EOF
