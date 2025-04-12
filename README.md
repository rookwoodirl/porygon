How to contribute to `commands/`!

1. [Get set up with git](https://docs.github.com/en/get-started/start-your-journey)
2. Create your own branch! 
    `git checkout -b command/hello-world` or something
3. Write your command! Use `hello.py` as an example.
```python
# hello.py


# Always use this function name!
def run():
    """
    Says hello!
    """
    return 'Hello, world!' # This is the response you see when you run `!hello`
```

4. Push your branch!
    `git add -A`
    `git commit -m "I made a command and it does _____"`
    `git push`

5. Create a *pull request* through github and tag me (rookwoodirl) as a reviewer!
