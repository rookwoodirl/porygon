from flask import render_template
import os

class WebObject:
    def __init__(self, name, path='', **kwargs):
        self.name = name
        self.path = path
        self.html = render_template(os.path.join('html', path, f'{name}.html'), **kwargs)

    def html(html):
        return self.html


class HoverPanel(WebObject):
    path = 'util'
    name = 'hover_panel'
    def __init__(self, text, image, style=None, redirect=''):
        if style is None:
            style = self.name
            
        self.style = render_template(os.path.join('css', self.path, f'{style}.css'))
        image = os.path.join('static', 'images', f'{image}')

        super().__init__(self.name, path=self.path, style=self.style, text=text, image=image, redirect=redirect)


class Grid(WebObject):
    path = 'util'
    name = 'grid'
    def __init__(self, contents, width='100%', height='100%', num_cols=2, num_rows=-1, style=None, ):
        if style is None:
            style = self.name
        if num_rows < 1:
            num_rows = len(contents) // num_cols
            
        self.style = render_template(os.path.join('css', self.path, f'{style}.css'), 
            num_rows=num_rows, 
            num_cols=num_cols, 
            width=width, 
            height=height)

        super().__init__(self.name, path=self.path, style=self.style, contents=contents)



class JavaCanvas(WebObject):
    path = 'util'
    name = 'processing'
    
    def __init__(self, script, **kwargs):
        super().__init__(self.name, path=self.path, script=script, **kwargs)