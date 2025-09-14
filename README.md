# Inspiration

We *love* video games.
From running around endless worlds in Minecraft, to catching them all in Pokemon, we knew that we wanted to create something at HackMIT that'd let us build these worlds from the ground up. But how exactly?

Stepping onto the MIT campus, we realized that many of these places could be turned into something cool. The ice rink we were working in could be a cool hockey game map. The empty hallways could be liminal spacing in a horror game. The classrooms could be a crime scene in a murder mystery! The list goes so on and on.

With the idea of a murder mystery and forensics-like game on our minds (and Ryan being too obsessed with Dexter), we decided to name our hack after TV's favorite forensic analyst to show just how immersively this project can be used. It's also the inspiration for the little game we've prepared at demo!

# What it does

Dexter is the ultimate tool for aspiring game-devs, scanning real-world environments to reconstruct them as their very own virtual maps, using state-of-the-art Mentra glasses as facilitators for scanning and feedback, alongside AI neural networks that we trained to infer the shape and size of the environment itself.

Kick it off by saying "Dexter, start recording..." and let Dexter see through your eyes, as he encodes and transmits real-time image data to Supabase, where these images are then cached, organized, and used by our neural network to create a point cloud rendering.

# How we built it

For interacting with the smart glasses, we used the MentraOS SDK in TypeScript as our primary codebase in terms of transcribing messages, recording through the glasses, and communicating with our backend.

For the 3D reconstruction, we fine-tuned and trained a state-of-the-art model, inferring the shape and structure of our surroundings by looking at both global and frame attention and applying a Depth Prediction Transformer. 

For the segmentation of the map (to view certain objects in isolation), we run projections from 2D segmented views using Segmented Anything (SAM). We conglomerate these into a 3d segmented map.

# Individual Contributions

We split the work pretty evenly between ourselves, playing to our interests and strengths. For Ryan and Tim, most of the focus was on getting familiar with the MentraOS and the systems design for the project, while Aaryan and Howard focused on working with the 3D reconstruction and segmentation of the environment. Regardless of our focuses, we made an active effort to communicate with each other at all stages of the development process, brainstorming together, and understanding what was going on at each level of this project.

# Challenges we ran into

Working with the Mentra glasses was definitely one of the main obstacles to overcome, as for all of us, it was our first time working with smart glasses, and we decided to take on the challenge of working with a prototype model. 

While our creativity drove us to the entertainment track, our creative differences also led to challenges in determining what the final vision of the project was, and ended up being a roadblock in progress. Looking back, there's a bit of humor that our biggest problem wouldn't be the coding, but the big idea itself.

Through these problems, we were able to move past them and push forward by encouraging honest communication and active listening, to make sure everyone's voice felt heard, while also seeing where we had common ground. It was a long process, but a fruitful one.

# Accomplishments that we're proud of

The demo game that we've produced to show the use-case of Dexter is something we're proud of, as it's something a bit more unorthodox from typical hackathon submissions, and it let us tap into our creative sides in a different way here (i.e. photography, video-editing, etc.).

# What we learned

We learned that we could do a LOT in 24 hours! The technical scale of the project for us at the start seemed insurmountable and more like a fever dream, but we were able to really push ourselves and get a working product at the end of it all.

# What's next for our project

If we were given more time for the project, we'd love to have explored how the Mentra's IMU capabilities could've assisted us in making faster, more rigorous renderings of the assets and environment. In addition, the integration of the Mentra Glasses with Mira AI seemed really cool, but we didn't have the time to explore how we could incorporate it. Last but not least, we realized in the late hours of the hackathon that depending on the sound you play onto the glasses, you could simulate haptic feedback as the glasses would vibrate, even without a haptic feedback API. It was a promising find, and we'd be psyched to explore that further, if given the chance.
