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
        image = os.path.join('static', 'images', f'{image}.png')

        super().__init__(self.name, path=self.path, style=self.style, text=text, image=image, redirect=redirect)


class Grid(WebObject):
    path = 'util'
    name = 'grid'
    def __init__(self, contents, width=2, height=-1, style=None):
        if style is None:
            style = self.name
        if height < 1:
            height = len(contents) // width
            
        self.style = render_template(os.path.join('css', self.path, f'{style}.css'), 
            height=height, 
            width=width, 
            cell_width='100%', 
            cell_height='100%')

        super().__init__(self.name, path=self.path, style=self.style, contents=contents)

