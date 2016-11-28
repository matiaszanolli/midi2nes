var neslySound = require('nesly-sound');

var midiFileParser = require('midi-file-parser');
var fs = require('fs')


// file = window.atob(file)

class Generator {
  constructor(track, context, name, timing) {
    this.track = track;
    this.generator = context[name];
    this.timing = timing;
  }

  generate() {
    this.generator(['C5', 'E5', 'G5', 'C6']).timing(this.timing);
  }
}

class Song {
  constructor(file) {
    var f = fs.readFileSync(file, 'binary')

    this.context = neslySound(); // the Nesly engine
    this.timing = 1/8; // the default timing
    this.midi = midiFileParser(f);

    this.tracks = {} // midi tracks
  }

  getMidiTrack(id) {
    return this.midi.tracks[id];
  }

  setTrack(name, track) {
    track = new Generator(track, this.context, name, this.timing)
  }

  write() {
    this.context.done();
    this.context.write();
  }

  generateTracks() {
    for(var track in this.tracks) {
      this.tracks[track].generate();
    }
  }
}

song = new Song('Adventure_Island_Level_1.mid');
song.setTrack('square1', song.getMidiTrack(0));
console.log(song.tracks.square1);
song.generateTracks();
song.write();

//song.square1(['C5', 'E5', 'G5', 'C6'])
//    .timing(1/8);

//song.done();
//song.write();
