
/**
 * This project is written in the Java variant "Processing"
 * 
 * It is loaded into the webpage using processing.min.js, which is
 *  a javascript library that allows Processing to be run out of the
 *  HTML Canvas element
 * 
 * This is just a pretty visualization that leverages OOP concepts
 *  like inheritence and interfaces
 */

// set up all the variables related to framerate
// calculate these ONCE at the start so we don't have to do it every frame
frames = 0;
int framerate = 30;
float increment = 2.0 * PI / framerate; // "once per second"
float framespct = 0;
float framespctincr = 1 / framerate; // addition is cheaper than division
framespctincr /= 2;

float midX, midY;

// setup some math stuff
public float damping(float x, float f, float t) {
    /* math formula for that "heartbeat" pattern */
    float r = 3*pow(2.716, -1*f*(x % (2*PI))) * sin(t*x % (2*PI));
    return r;
}


// global variables setup() and draw() can set and read, respectively
FlowerCircle c;
TextBox 
    tbRadius,
    tbColor,
    tbDamp;
Drawable[] thingsToDraw;


void setup() {
    // some high-level things
    strokeWeight(2);
    size(500, 600);
    background(255);
    frameRate(framerate);

    // so we don't have to caclculate this every frame
    midX = width/2;
    midY = height/2;


    // the circle!
    c = new FlowerCircle(150, 12, 0.2, midX, 200);

    // text boxes that display the stats of the circle
    // would have liked to do this with anonymous subclassing but processing.min.js doesn't support that!
    tbRadius = new TextBox(10, 500, 200, 30);
    tbColor  = new TextBox(10, 530, 200, 30);
    tbDamp   = new TextBox(10, 560, 200, 30);

    // draw our pretty things!
    thingsToDraw = { c, tbRadius, tbColor, tbDamp };

}

void draw() {
    // draw the background
    noStroke();
    background(0);
    fill(0);

    // increase frame count
    frames++;
    framespct += framespctincr;


    // draw all our pretty things
    for (Drawable thing : thingsToDraw)
        thing.draw();
}

interface Drawable {
    void draw();
}

class Circle implements Drawable {
    /*
        It's a circle!
    */

    protected float radius, centerX, centerY, rotation, x, y;
    Color c = color(0,0,0,255);


    Circle(float radius, float centerX, float centerY, float rotationSpeed, float initialRotation) {
        this.radius = radius;
        this.centerX = centerX;
        this.centerY = centerY;
        this.rotationSpeed = rotationSpeed;
        this.initialRotation = initialRotation;
    }

    void draw() {
        fill(0,0,0,0); /* transparent */
        stroke(this.c); /* black line */
        float x = radius/2 * cos(this.rotationSpeed * 2 * PI * framespct + this.initialRotation) + this.centerX;
        float y = radius/2 * sin(this.rotationSpeed * 2 * PI * framespct + this.initialRotation) + this.centerY;
        ellipse(x, y, this.radius, this.radius);
    }
}

class FlowerCircle extends Circle {
    /*
        It's a circle...
            ... made up of circles!
    */
    Circle[] petals;
    FlowerCircle(float radius, int numCircles, float rotationSpeed, float centerX, float centerY) {
        super(radius, rotationSpeed, centerX, centerY, 0);
        this.petals = new Circle[numCircles];
        Circle parent = this;

        for (int i = 0; i < numCircles; i++) {
            float pctrotation = i/numCircles; // permanent variable
            this.petals[i] = new Circle(radius, centerX, centerY, rotationSpeed, 2*PI * pctrotation);
        }
    }

    void draw() {
        // change some properties based on the damping function...
        float damp = damping(sin(framespct % 1.0 * 2 * PI) + 1, 10, 1);
        this.radius = 150 + -100 * damp;
        this.c = color(
                255, 
                255 - damp*5 * 255,
                255 - damp*5 * 255);


        // spread it to the children!
        for (int i = 0; i < this.petals.length; i++) {
            Circle circle = this.petals[i];
            circle.c = this.c;
            circle.radius = this.radius;

            this.petals[i].draw();
        }

        // update the text boxes with the relevant information
        tbRadius.words = "radius: " + (Math.round(this.radius * 1000.0) / 1000.0);
        tbColor.words = "color: (" + red(this.c) + ", " + green(this.c) + ", " + blue(this.c) + ")";
        tbDamp.words = "damp: " + (Math.round(damp * 1000.0) / 1000.0);
    }
}


class TextBox implements Drawable {
    float x, y, fontSize;
    String words;
    TextBox(x, y, width, height) {
        this.x = x;
        this.y = y;
        this.fontSize = height;
        this.width = width;
        this.height = height;
        this.words = "nice";
    }
    void draw() {
        this.writeText();
    }

    void writeText() {
        stroke(0);
        fill(0);
        rect(this.x, this.y - this.height*0.9, this.width, this.height)
        textSize(this.fontSize);
        stroke(0);
        fill(255);
        text(this.words, this.x, this.y); 
    }
}
