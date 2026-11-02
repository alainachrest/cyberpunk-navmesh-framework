// usage: kark <in.segs> <outdir>   writes seg_000.bin ... decompressed
use std::io::Read;
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let mut d = Vec::new(); std::fs::File::open(&a[1]).unwrap().read_to_end(&mut d).unwrap();
    std::fs::create_dir_all(&a[2]).unwrap();
    let u32at = |p: usize, d: &Vec<u8>| u32::from_le_bytes(d[p..p+4].try_into().unwrap()) as usize;
    let n = u32at(4, &d); let mut p = 8;
    for i in 0..n {
        let z = u32at(p, &d); let s = u32at(p+4, &d); p += 8;
        let raw = &d[p..p+z]; p += z;
        let out = if z == s { raw.to_vec() } else {
            assert!(&raw[0..4] == b"KARK");
            let size = u32::from_le_bytes(raw[4..8].try_into().unwrap()) as usize;
            let mut o = vec![0u8; size];
            let mut ex = oozextract::Extractor::new();
            ex.read_from_slice(&raw[8..], &mut o).unwrap();
            o
        };
        std::fs::write(format!("{}/seg_{:03}.bin", a[2], i), &out).unwrap();
    }
    println!("{} segments", n);
}
