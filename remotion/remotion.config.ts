import { Config } from "@remotion/cli/config";

// 1080p30 matches the factory's long-video output. Concurrency stays default:
// a GitHub ubuntu runner has 4 cores and Remotion scales to it.
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setCodec("h264");
Config.setCrf(18);
