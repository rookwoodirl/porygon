import chess
import chess.pgn
import cairosvg
from PIL import Image
from io import BytesIO

def pgn_to_gif(pgn_file, output_file):
    # Read PGN file
    with open(pgn_file) as f:
        game = chess.pgn.read_game(f)

    # Initialize a chess board
    board = chess.Board()

    # List to store frames for GIF
    frames = []

    # Iterate through each move in the game
    for move in game.mainline_moves():
        # Make the move on the board
        board.push(move)

        # Render the chess board as an SVG
        svg = chess.svg.board(board=board)

        # Convert SVG to PNG using cairosvg
        png_data = cairosvg.svg2png(bytestring=svg.encode('utf-8'))

        # Convert PNG data to PIL Image
        image = Image.open(BytesIO(png_data))

        frames.append(image)

    # Save frames as GIF
    frames[0].save(output_file, save_all=True, append_images=frames[1:], optimize=False, duration=500, loop=0)

if __name__ == "__main__":
    # Replace 'your_game.pgn' with the actual PGN file name
    pgn_file = 'chess.pgn'

    # Replace 'output.gif' with the desired output GIF file name
    output_file = 'chess.gif'

    pgn_to_gif(pgn_file, output_file)
