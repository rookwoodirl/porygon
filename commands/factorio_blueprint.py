import base64
import zlib
import json
import os, requests, sys
from PIL import Image

# Factorio API Stuff https://wiki.factorio.com/Blueprint_string_format





class BlueprintImageConstructor:

    def __init__(self, bp_file, assets_dir):
        self.assets_dir = assets_dir
        self.bp_file = bp_file

        blueprints = self.decode_factorio_blueprint()
        
        self.imgs = [self.create_image(blueprint) for blueprint in blueprints]

    def get_image_files(self):
        return self.imgs

    def download_image(self, url, save_directory, filename):
        # Ensure the save directory exists
        os.makedirs(save_directory, exist_ok=True)

        # Make a GET request to the URL
        response = requests.get(url)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Build the complete file path
            file_path = os.path.join(save_directory, filename)

            # Save the image to the specified directory
            with open(file_path, 'wb') as file:
                file.write(response.content)

            print(f"Image downloaded and saved to: {file_path}")
        else:
            print(f"Failed to download image. Status code: {response.status_code}")


    def get_asset(self, asset_name):
        
        
        # scraping :^)
        fname = asset_name[0].upper() + asset_name[1:].lower().replace('-', '_') + '.png'
        
        if fname not in os.listdir(os.path.join(self.assets_dir, 'factorio', 'icons')):
            image_url = "https://wiki.factorio.com/images/{}".format(fname) # Fast_transport_belt

            self.download_image(image_url, os.path.join(self.assets_dir, 'factorio', 'icons'), fname)
        
        return Image.open(os.path.join(self.assets_dir, 'factorio', 'icons', fname))

    def decode_factorio_blueprint(self):

        # Example Factorio blueprint string
        with open(self.bp_file, 'r') as f:
            blueprint_string = ''.join(f.readlines())

            # Skip the first byte (version byte)
            compressed_data = base64.b64decode(blueprint_string[1:])

            # Decompress the data using zlib inflate
            json_string = zlib.decompress(compressed_data).decode('utf8')

            # Load the JSON string into a Python dictionary
            blueprint_data = json.loads(json_string)

        # break up blueprints because they can be huge
        blueprints = []
        # multiple
        if 'blueprint_book' in blueprint_data:
            blueprint_data = {i : b for i, b in zip(range(len(blueprint_data['blueprint_book']['blueprints'])), blueprint_data['blueprint_book']['blueprints'])}
        # single
        else:
            blueprint_data = {0 : blueprint_data}


        for bp in blueprint_data:
            fname = 'factorio_bp_{}.json'.format(len(blueprints))
            with open(fname, 'w+') as f:
                f.write(json.dumps(blueprint_data[bp]['blueprint'], indent=2))
            blueprints.append(fname)


        # might be super super big
        return blueprints
    
    def create_image(self, blueprint_path):
        sizes = {
            'beacon' : (3, 3),
            'substation' : (2, 2),
            'assembling-machine' : (3, 3),
            'assembling-machine-2' : (3, 3),
            'assembling-machine-3' : (3, 3)
        }
        
        # Load the JSON string into a Python dictionary
        with open(blueprint_path, 'r') as f:
            blueprint = json.loads(''.join(f.readlines()))

        image_array = []
        xmin, xmax, ymin, ymax = 0, 0, 0, 0
        
        for entity in blueprint['tiles'] + blueprint['entities'] if 'tiles' in blueprint else blueprint['entities']:
            image_array.append((
                entity['name'], 
                entity['position']['x'], # 0 centered
                entity['position']['y'],
                0 if 'direction' not in entity else entity['direction']
            ))
            if xmin > entity['position']['x']:
                xmin = entity['position']['x']
            if xmax < entity['position']['x']:
                xmax = entity['position']['x']
            if ymin > entity['position']['y']:
                ymin = entity['position']['y']
            if ymax < entity['position']['y']:
                ymax = entity['position']['y']


        px = 64 # default size of a tile in factorio
        bpwidth, bpheight = px * int(xmax - xmin), px * int(ymax - ymin)


        # Create a new background image
        result = Image.new('RGBA', (bpwidth, bpheight))

        # Iterate over the array of (x, y, img) and paste each image onto the background
        for name, x, y, direction in image_array:
            # Open the image to be pasted
            img = self.get_asset(name)
            # Paste the image onto the background at the specified position

            if name in sizes:
                j, k = sizes[name]
                img = img.resize((img.width * j, img.height * k))
                x, y = x - j // 2, y - k // 2

            img = img.rotate(45 * direction)

            result.paste(img, (px * int(x - xmin), px * int(y - ymin)), img)

        # result.show()

        result.save(os.path.join('commands', 'factorio_bp.png'))

        return os.path.join('commands', 'factorio_bp.png')



if __name__ == "__main__":

    bp_constructor = BlueprintImageConstructor('factorio.bp', os.path.join('..', 'assets'))
