import { AppServer, AppSession, ViewType, AuthenticatedRequest, PhotoData } from '@mentra/sdk';
import { Request, Response } from 'express';
import * as ejs from 'ejs';
import * as path from 'path';
import { supabase } from './supabase';
import * as constants from './util/constants';

// interface for a stored photo with metadata
interface StoredPhoto {
  requestId: string;
  buffer: Buffer;
  timestamp: Date;
  userId: string;
  mimeType: string;
  filename: string;
  size: number;
}

const PACKAGE_NAME =
  process.env.PACKAGE_NAME ??
  (() => {
    throw new Error('PACKAGE_NAME is not set in .env file');
  })();
const MENTRAOS_API_KEY =
  process.env.MENTRAOS_API_KEY ??
  (() => {
    throw new Error('MENTRAOS_API_KEY is not set in .env file');
  })();
const PORT = parseInt(process.env.PORT || '3000');

/**
 * Photo Taker App with webview functionality for displaying photos
 * Extends AppServer to provide photo taking and webview display capabilities
 */
class ForensicsApp extends AppServer {
  private photos: Map<string, StoredPhoto> = new Map(); // Store photos by userId
  private latestPhotoTimestamp: Map<string, number> = new Map(); // Track latest photo timestamp per user
  private isStreamingPhotos: Map<string, boolean> = new Map(); // Track if we are streaming photos for a user
  private nextPhotoTime: Map<string, number> = new Map(); // Track next photo time for a user
  private recordingSetup: Map<
    string,
    { scene?: string; object?: string; step: 'idle' | 'waiting_for_scene' | 'waiting_for_object' | 'ready' }
  > = new Map(); // Track recording setup per user

  constructor() {
    super({
      packageName: PACKAGE_NAME,
      apiKey: MENTRAOS_API_KEY,
      port: PORT,
    });
    this.setupWebviewRoutes();
  }

  /**
   * Handle new session creation and button press events
   */
  protected async onSession(session: AppSession, sessionId: string, userId: string): Promise<void> {
    // this gets called whenever a user launches the app
    this.logger.info(`Session started for user ${userId}`);

    // set the initial state of the user
    this.isStreamingPhotos.set(userId, false);
    this.nextPhotoTime.set(userId, Date.now());
    this.recordingSetup.set(userId, { step: 'idle' });

    // set up transcription listener to account for streaming
    const recordingCommands = session.events.onTranscription(async (data) => {
      const isFinal: boolean = data.isFinal;

      if (isFinal) {
        // process transcribed text
        const transcribedText = data.text
          .toLowerCase()
          .replace(/[^\w\s]/g, '')
          .replace(/\s+/g, ' ')
          .trim();

        console.log(`Transcription: "${transcribedText}"`);

        // Photo handling with regex matching
        const stopMatch = transcribedText.match(constants.STOP_RECORDING_REGEX);
        const startMatch = transcribedText.match(constants.START_RECORDING_REGEX);

        if (stopMatch) {
          // Check if currently recording
          if (!this.isStreamingPhotos.get(userId)) {
            session.logger.info(`User ${userId} tried to stop recording but not currently recording`);
            try {
              await session.audio.speak('Not currently recording', {
                model_id: 'eleven_flash_v2_5',
                voice_settings: {
                  speed: 1.0,
                  stability: 0.7,
                },
              });
            } catch (error) {
              session.logger.error(`TTS error: ${error}`);
            }
            return;
          }

          session.logger.info(`Disabling streaming property!`);
          this.isStreamingPhotos.set(userId, false);
          this.nextPhotoTime.delete(userId);

          // stop recording
          try {
            await session.audio.speak('Recording stopped', {
              model_id: 'eleven_flash_v2_5',
              voice_settings: {
                speed: 1.0,
                stability: 0.7,
              },
            });
          } catch (error) {
            session.logger.error(`TTS error: ${error}`);
          }
        } else if (startMatch) {
          // check if already recording
          if (this.isStreamingPhotos.get(userId)) {
            session.logger.info(`User ${userId} is already recording`);
            try {
              await session.audio.speak('Recording already in progress', {
                model_id: 'eleven_flash_v2_5',
                voice_settings: {
                  speed: 1.0,
                  stability: 0.7,
                },
              });
            } catch (error) {
              session.logger.error(`TTS error: ${error}`);
            }
            return;
          }

          // Extract scene and object from regex match
          const sceneName = startMatch[1].trim().replace(/\s+/g, '_').toLowerCase();
          const objectName = startMatch[2].trim().replace(/\s+/g, '_').toLowerCase();

          session.logger.info(`Starting recording for scene: ${sceneName}, object: ${objectName}`);

          // Create scene folder if it doesn't exist
          await this.ensureSceneFolder(sceneName);

          // Set up recording with extracted scene and object
          this.recordingSetup.set(userId, {
            scene: sceneName,
            object: objectName,
            step: 'ready',
          });

          // Start recording
          this.isStreamingPhotos.set(userId, true);

          try {
            await session.audio.speak(`Recording started for ${sceneName} - ${objectName}`, {
              model_id: 'eleven_flash_v2_5',
              voice_settings: {
                speed: 1.0,
                stability: 0.7,
              },
            });
          } catch (error) {
            session.logger.error(`TTS error: ${error}`);
          }
        }
      }
    });

    // this gets called whenever a user presses a button
    const takePhoto = session.events.onButtonPress(async (button) => {
      this.logger.info(`Button pressed: ${button.buttonId}, type: ${button.pressType}`);

      if (button.pressType === 'long') {
        // the user held the button, so we toggle the streaming mode
        this.isStreamingPhotos.set(userId, !this.isStreamingPhotos.get(userId));
        this.logger.info(`Streaming photos for user ${userId} is now ${this.isStreamingPhotos.get(userId)}`);
        return;
      } else {
        session.layouts.showTextWall('Button pressed, about to take photo', { durationMs: 4000 });
        // the user pressed the button, so we take a single photo
        try {
          // first, get the photo
          const photo = await session.camera.requestPhoto();
          // if there was an error, log it
          this.logger.info(`Photo taken for user ${userId}, timestamp: ${photo.timestamp}`);
          this.cachePhoto(photo, userId);
        } catch (error) {
          this.logger.error(`Error taking photo: ${error}`);
        }
      }
    });

    // Janitors
    this.addCleanupHandler(recordingCommands);
    this.addCleanupHandler(takePhoto);

    // repeatedly check if we are in streaming mode and if we are ready to take another photo
    setInterval(async () => {
      if (this.isStreamingPhotos.get(userId) && Date.now() > (this.nextPhotoTime.get(userId) ?? 0)) {
        try {
          // set the next photos for 30 seconds from now, as a fallback if this fails
          this.nextPhotoTime.set(userId, Date.now() + 30000);

          // actually take the photo
          const photo = await session.camera.requestPhoto();

          // set the next photo time to now, since we are ready to take another photo
          this.nextPhotoTime.set(userId, Date.now());

          // cache the photo for display
          this.cachePhoto(photo, userId);
        } catch (error) {
          this.logger.error(`Error auto-taking photo: ${error}`);
        }
      }
    }, 1000);
  }

  protected async onStop(sessionId: string, userId: string, reason: string): Promise<void> {
    // clean up the user's state
    this.isStreamingPhotos.set(userId, false);
    this.nextPhotoTime.delete(userId);
    this.recordingSetup.delete(userId);
    this.logger.info(`Session stopped for user ${userId}, reason: ${reason}`);
  }

  /**
   * Ensure scene folder exists in the main Supabase bucket
   */
  private async ensureSceneFolder(sceneName: string): Promise<void> {
    try {
      // Create a placeholder file to ensure the scene folder exists
      const bucket = process.env.SUPABASE_BUCKET!;
      const sceneFolderPath = `${sceneName}/.folder_placeholder`;

      // Try to create the folder by uploading a small placeholder
      const { error: createError } = await supabase.storage
        .from(bucket)
        .upload(sceneFolderPath, new Blob([''], { type: 'text/plain' }), {
          upsert: true,
        });

      if (createError) {
        this.logger.error(`Error creating scene folder ${sceneName}: ${createError.message}`);
      } else {
        this.logger.info(`Ensured scene folder exists: ${sceneName}`);
        // Clean up the placeholder file
        await supabase.storage.from(bucket).remove([sceneFolderPath]);
      }
    } catch (error) {
      this.logger.error(`Error ensuring scene folder: ${error}`);
    }
  }

  /**
   * Cache a photo for display and put into Supabase table
   */
  private async cachePhoto(photo: PhotoData, userId: string) {
    const cachedPhoto: StoredPhoto = {
      requestId: photo.requestId,
      buffer: photo.buffer,
      timestamp: photo.timestamp,
      userId,
      mimeType: photo.mimeType,
      filename: photo.filename,
      size: photo.size,
    };

    this.photos.set(userId, cachedPhoto);
    this.latestPhotoTimestamp.set(userId, cachedPhoto.timestamp.getTime());

    // Get current recording setup for this user
    const setup = this.recordingSetup.get(userId);
    if (!setup || !setup.scene || !setup.object) {
      this.logger.error(`No recording setup found for user ${userId}`);
      return;
    }

    const bucket = process.env.SUPABASE_BUCKET!;
    const ext = photo.mimeType === 'image/jpeg' ? 'jpg' : 'png';
    const objectPath = `${setup.scene}/${setup.object}/${photo.requestId}.${ext}`;

    // upload to main bucket with folder structure
    this.logger.info(`Uploading photo to bucket ${bucket} at path: ${objectPath}`);
    const { error: uploadErr } = await supabase.storage.from(bucket).upload(objectPath, cachedPhoto.buffer, {
      contentType: cachedPhoto.mimeType,
      upsert: true,
    });

    if (uploadErr) {
      this.logger.error(`Storage upload failed: ${uploadErr.message}`);
      return;
    }

    // insert metadata into table with scene/object info
    const { error: insertErr } = await supabase.from('mentra_scenes').insert({
      user_id: userId,
      request_id: photo.requestId,
      path: objectPath,
      mime_type: photo.mimeType,
      size: photo.size,
      captured_at: photo.timestamp.toISOString(),
      scene: setup.scene,
      object: setup.object,
    });

    if (insertErr) {
      this.logger.error(`Insert failed: ${insertErr.message}`);
    } else {
      this.logger.info(`Saved photo to scene ${setup.scene}, object ${setup.object}: ${objectPath}`);
    }
  }

  /**
   * Set up webview routes for photo display functionality
   * take latest photo from supabase table and return a signed url
   */
  private setupWebviewRoutes(): void {
    const app = this.getExpressApp();

    // get latest photo from supabase table
    app.get('/api/latest-photo', async (req: any, res: any) => {
      const userId = (req as AuthenticatedRequest).authUserId;
      if (!userId) return res.status(401).json({ error: 'Not authenticated' });

      // latest row from supabase table
      const { data: row, error } = await supabase
        .from('mentra_scenes')
        .select('request_id, path, mime_type, size, captured_at')
        .eq('user_id', userId)
        .order('captured_at', { ascending: false })
        .limit(1)
        .maybeSingle();

      if (error) return res.status(500).json({ error: error.message });
      if (!row) return res.status(404).json({ error: 'No photo available' });

      // create signed URL from storage
      const bucket = process.env.SUPABASE_BUCKET!;
      const { data: signed, error: signErr } = await supabase.storage.from(bucket).createSignedUrl(row.path, 60 * 5); // 5 minutes

      if (signErr || !signed?.signedUrl) {
        return res.status(500).json({ error: signErr?.message ?? 'Failed to sign URL' });
      }

      res.json({
        requestId: row.request_id,
        timestamp: new Date(row.captured_at).getTime(),
        hasPhoto: true,
        signedUrl: signed.signedUrl, // client load this directly
        mimeType: row.mime_type,
        size: row.size,
      });
    });

    // stream specific photo by requestId via server proxy
    app.get('/api/photo/:requestId', async (req: any, res: any) => {
      const userId = (req as AuthenticatedRequest).authUserId;
      if (!userId) return res.status(401).json({ error: 'Not authenticated' });

      const requestId = req.params.requestId;

      // look up path and metadata in supabase table
      const { data: row, error } = await supabase
        .from('mentra_scenes')
        .select('path, mime_type')
        .eq('user_id', userId)
        .eq('request_id', requestId)
        .maybeSingle();

      if (error) return res.status(500).json({ error: error.message });
      if (!row) return res.status(404).json({ error: 'Photo not found' });

      // download from storage and pipe back
      const bucket = process.env.SUPABASE_BUCKET!;
      const { data: file, error: dlErr } = await supabase.storage.from(bucket).download(row.path);
      if (dlErr || !file) return res.status(500).json({ error: dlErr?.message ?? 'Failed to download photo' });

      const arrayBuf = await file.arrayBuffer();
      res.set({
        'Content-Type': row.mime_type,
        'Cache-Control': 'no-cache',
      });
      res.send(Buffer.from(arrayBuf));
    });

    // webview route
    app.get('/webview', async (req: any, res: any) => {
      const userId = (req as AuthenticatedRequest).authUserId;
      if (!userId) {
        res.status(401).send(`
          <html>
            <head><title>Photo Viewer - Not Authenticated</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
              <h1>Please open this page from the MentraOS app</h1>
            </body>
          </html>
        `);
        return;
      }

      const templatePath = path.join(process.cwd(), 'views', 'photo-viewer.ejs');
      const html = await ejs.renderFile(templatePath, {});
      res.send(html);
    });
  }
}

// Start the server
// DEV CONSOLE URL: https://console.mentra.glass/
// Get your webhook URL from ngrok (or whatever public URL you have)
const app = new ForensicsApp();

app.start().catch(console.error);
