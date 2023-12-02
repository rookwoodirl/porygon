import base64
import zlib, zstandard, lzma
import json

def decode_factorio_blueprint(blueprint_string):
    # Skip the first byte (version byte)
    compressed_data = base64.b64decode(blueprint_string[1:])

    # Decompress the data using zlib inflate
    json_string = zlib.decompress(compressed_data).decode('utf8')

    # Load the JSON string into a Python dictionary
    blueprint_data = json.loads(json_string)

    return blueprint_data

if __name__ == "__main__":
    # Example Factorio blueprint string
    with open('factorio.bp', 'r') as f:
        example_blueprint_string = ''.join(f.readlines())

    # Decode Factorio blueprint string
    decoded_blueprint = decode_factorio_blueprint(example_blueprint_string)

    # Print the decoded JSON
    with open('factorio.json', 'w+') as f:
        f.write(json.dumps(decoded_blueprint, indent=2))
