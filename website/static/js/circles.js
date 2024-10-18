frames = 0;
void setup() {
    print("wahoo!");
    size(500, 500);
    background(255);
}
void draw() {
    background(255);
    fill(0);
    ellipse(width/2 + 50 * sin((frames / 60) * 2 * PI), width/2, 50, 50);
    frames++;
}