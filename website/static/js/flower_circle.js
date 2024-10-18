color
  DARKGRAY = #A9A9A9,
  LIGHTGRAY = #D3D3D3
  ;
  

int frameCount = 0;
int totalFrames = 100; // Total frames for the GIF
  


int midX;
int midY;


public class RadiallyTrackedCircle {
  float size = 1;
  color col = #ffffff;
  protected float x = 0;
  protected float y = 0;
  
  float centerX = 0;
  float centerY = 0;
  
  float angle = 0.0; // angle from the center
  float distance = 0;
  
  PImage img;
  
  public RadiallyTrackedCircle(float size, color col) {
    this.size = size;
    this.col = color(col);
    
    // add it to the circles we want to track
    circles = (RadiallyTrackedCircle[]) concat(circles, new RadiallyTrackedCircle[] { this });
  }
  
  float distance() {
    return calcDistance(0, 0, this.centerX, this.centerY);
  }
  float angle() {
    return calcAngle(0, 0, this.centerX, this.centerY);
  }
  
  public void center() {
    this.centerX = midX;
    this.centerY = midY;
  }
  
  public void draw() {
    noFill();
    stroke(#000000); // no outline on circle
    circle(this.x, this.y, this.size);
  }
  
  
  void setCoords() {
    this.center();
    this.distance = this.distance();
    this.angle = this.angle();
  
    
    this.x = this.centerX + this.distance * cos(this.angle);
    this.y = this.centerY + this.distance * sin(this.angle);
  }
  
  
  public void render() {
    this.setCoords();
    this.draw();
  }
}


public class FlowerCircle extends RadiallyTrackedCircle {
    int numCircles;
    RadiallyTrackedCircle[] orbitingCircles;
    public FlowerCircle(float size, color col, int numCircles) {
      super(size, col);
      this.numCircles = numCircles;
      this.orbitingCircles = new RadiallyTrackedCircle[numCircles];
      
      RadiallyTrackedCircle parent = this;
      
      
      // set up the concentric circles
      for (int i = 0; i < numCircles; i++) {
        int j = i; // don't ask
        orbitingCircles[i] = new RadiallyTrackedCircle(parent.size, parent.col) {
          void center() {
            this.centerX = parent.x;
            this.centerY = parent.y;
          }
          float angle() {
            return parent.angle + 2*PI * j/numCircles;
          }
          float distance() {
            this.size = parent.size;
            return parent.size/2;
          }
        };
      }
      
      
    }
    
    
}


FlowerCircle flower;



void draw() {
  print("nice!");
  // black background
  background(DARKGRAY);
  
  
  // render all the circles!
  for (RadiallyTrackedCircle c : circles)
    c.render();
    
  
}

void setup() {
  print("wahoo!");
  frameRate(10);
  
  // set up the rendering environment
  imageMode(CENTER);
  size(500,500);
  
  // precalculate midX and midY to avoid doing this calculation 1000000 times every frame
  midX = int(width/2.0);
  midY = int(height/2.0);
  
  
  /* 
   *  THIS IS THE INTERESTING STUFF
   */
  
  // (RED) set up a normal circle that floats the opposite side of the mouse
  flower = new FlowerCircle(100, LIGHTGRAY, 10) {
    public float distance() {
      // A * e^(-at)
      this.size = 180 + 20.0*damping(this.angle, 2, 9);
      return 0;
    }
    public void draw() {
      return; // don't show the outer circle
    }
    
    public float angle() {
      // spin it 1 rotation every 5 seconds
      return 2.0*PI * frameCount / frameRate / 5;
    }
  };
  
  
  
}



// this gets used in RadialTracking to know the things we need to render
RadiallyTrackedCircle[] circles = new RadiallyTrackedCircle[0];

static float calcDistance(float x0, float y0, float x1, float y1) {
  float d = sqrt((x0 - x1) * (x0 - x1) + (y0 - y1) * (y0 - y1));
  return d;
}

static float calcAngle(float x0, float y0, float x1, float y1) {
  float j = x1 - x0;
  if (j == 0)
    return PI/-2;

  float d = atan((y1-y0)/(x1-x0));
  
  if (j < 0)
    d += PI;
  
  return d;
}



