var neslySound = require('nesly-sound');

var midiFileParser = require('midi-file-parser');
var fs = require('fs');
var _ = require('lodash');
var tonal = require('tonal');


// file = window.atob(file)

class Generator {
  constructor(track, context, name, timing) {
    this.track = track;
    this.generator = context[name];
    this.timing = timing;
    this.processed = [];
  }

  convertNote(note) {
    console.log('Converting ', note)
    return tonal.note.fromMidi(note.noteNumber);
  }

  notes(note) {
    return note.subtype === 'noteOn';
  }

  generate() {
    this.processed = _.map(this.track.filter(this.notes), (note) => {
      return this.convertNote(note);
    });
    console.log(this.processed)
    this.generator(this.processed).timing(this.timing);
  }
}

class Song {
  constructor(file) {
    const f = fs.readFileSync(file, 'binary');

    this.context = neslySound(); // the Nesly engine
    this.timing = 1/8; // the default timing
    this.midi = midiFileParser(f);

    this.tracks = {} // midi tracks
  }

  // Gets a midi unprocessed track from its id
  getMidiTrack(id) {
    console.log('Getting MIDI track: ', id)
    return this.midi.tracks[id];
  }

  // Sets an unprocessed given track
  setTrack(name, track) {
    console.log('Setting MIDI track: ', name)
    this.tracks[name] = new Generator(track, this.context, name, this.timing)
  }

  // Outputs the NES ASM source code
  write() {
    console.log('Writing...')
    this.context.done();
    this.context.write();
  }

  // Processes all tracks on the engine
  generateTracks() {
    for(var track in this.tracks) {
      this.tracks[track].generate();
    }
  }
}

song = new Song('Adventure_Island_Level_1.mid');
song.setTrack('square1', song.getMidiTrack(1));
song.generateTracks();
// fs.writeFile('./build/tracks.json', JSON.stringify(song.midi.tracks, null, 2) , 'utf-8');
song.write();

//song.square1(['C5', 'E5', 'G5', 'C6'])
//    .timing(1/8);

//song.done();
//song.write();
