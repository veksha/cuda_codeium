from cudatext import *
import cudatext_cmd as cmds
import cudatext_keys as keys

class Dialog:
    h_dlg = None
    x, y = None, None
    
    @classmethod
    def save_position(cls, id_dlg, id_ctl, data='', info=''):
        if cls.h_dlg is not None:
            props = dlg_proc(cls.h_dlg, DLG_PROP_GET)
            cls.x = props['x']
            cls.y = props['y']
    
    @classmethod
    def on_key_down(cls, id_dlg, id_ctl, data='', info=''):
        key, mod = data
        if mod == 'c' and key == keys.VK_ENTER:
            cls.on_send(id_dlg, id_ctl, info=info)
            
    @classmethod
    def on_send(cls, id_dlg, id_ctl, data='', info=''):
        callback = info
        
        cls.save_position(id_dlg, id_ctl)
        dlg_proc(id_dlg, DLG_HIDE)
        
        memo = Editor(dlg_proc(id_dlg, DLG_CTL_HANDLE, name='memo'))
        callback(memo.get_text_all())
    
    @classmethod
    def input(cls, callback):
        if cls.h_dlg is not None:
            
            props = dlg_proc(cls.h_dlg, DLG_PROP_GET)
            dlg_visible = props['vis']
            
            if not dlg_visible:
                dlg_proc(cls.h_dlg, DLG_PROP_SET, prop={
                    'x': cls.x,
                    'y': cls.y,
                })
            
            dlg_proc(cls.h_dlg, DLG_CTL_FOCUS, name='memo')
            dlg_proc(cls.h_dlg, DLG_SHOW_NONMODAL)
            return
        
        h=dlg_proc(0, DLG_CREATE)
        dlg_proc(h, DLG_PROP_SET, prop={
            'cap': 'Codeium chat',
            'w': 450,
            'h': 300,
            'topmost': True,
            'on_close': cls.save_position,
        })
        cls.h_dlg = h
        
        _, font_size = ed.get_prop(PROP_FONT)
        font_scale = ed.get_prop(PROP_SCALE_FONT)
        
        idc=dlg_proc(h, DLG_CTL_ADD, 'label');
        dlg_proc(h, DLG_CTL_PROP_SET, index=idc, prop={
            'cap': 'Enter your question below.',
            'align': ALIGN_TOP,
            'sp_a': 6,
        })
        
        idc=dlg_proc(h, DLG_CTL_ADD, 'editor');
        dlg_proc(h, DLG_CTL_PROP_SET, index=idc, prop={
            'name': 'memo',
            'align': ALIGN_CLIENT,
            'sp_a': 6,
            'font_size': font_size,
            'on_key_down': lambda *args,**kwargs: cls.on_key_down(*args,**kwargs,info=callback),
        })
        memo = Editor(dlg_proc(h, DLG_CTL_HANDLE, index=idc))
        memo.set_prop(PROP_SCALE_FONT, font_scale)
        memo.set_prop(PROP_WRAP, True)
        memo.set_prop(PROP_GUTTER_NUM, False)
        memo.set_prop(PROP_GUTTER_STATES, False)
        memo.set_prop(PROP_GUTTER_FOLD, False)
        memo.set_prop(PROP_GUTTER_BM, False)
        
        idc=dlg_proc(h, DLG_CTL_ADD, 'panel');
        dlg_proc(h, DLG_CTL_PROP_SET, index=idc, prop={
           'name': 'panel',
           'h': 35,
           'align': ALIGN_BOTTOM,
        })
        
        idc=dlg_proc(h, DLG_CTL_ADD, 'label');
        dlg_proc(h, DLG_CTL_PROP_SET, index=idc, prop={
           'cap': 'Ctrl+Enter to send.',
           'p': 'panel',
           'align': ALIGN_RIGHT,
           'sp_a': 6,
        })
        
        idc=dlg_proc(h, DLG_CTL_ADD, 'button');
        dlg_proc(h, DLG_CTL_PROP_SET, index=idc, prop={
           'name': 'btn_ok',
           'cap': 'Send',
           'p': 'panel',
           'align': ALIGN_RIGHT,
           'sp_l': 6,
           'sp_r': 6,
           'sp_b': 6,
           'on_change': lambda *args,**kwargs: cls.on_send(*args,**kwargs,info=callback),
           'ex0': True,
        })
        
        dlg_proc(h, DLG_SCALE)
        dlg_proc(h, DLG_SHOW_NONMODAL)

