__all__ = [
    'preview',
    'workers',
]

def run():
    from pif.ui.x.preview import PreviewWindow
    PreviewWindow().run()
