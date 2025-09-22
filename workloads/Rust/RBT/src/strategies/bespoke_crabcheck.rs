use {
    crate::implementation::{
        Color::{
            self,
            *,
        },
        Tree::{
            self,
            *,
        },
        blacken,
        elems,
    },
    crabcheck::quickcheck::{
        Arbitrary,
        Mutate,
    },
    rand::Rng,
};

fn choose<R: Rng>(min: usize, max: usize, r: &mut R) -> usize {
    usize::generate(r, max - min + 1) + min
}

pub(crate) fn gen_kvs<R: Rng>(size: usize, r: &mut R) -> Vec<(i32, i32)> {
    let mut kvs = Vec::with_capacity(size);
    for _ in 0..size {
        let k = i32::generate(r, size);
        let v = i32::generate(r, size);
        kvs.push((k, v));
    }
    kvs
}

fn balance(col: Color, tl: Tree, key: i32, val: i32, tr: Tree) -> Tree {
    match (col, tl, key, val, tr) {
        (B, T(R, box T(R, a, x, vx, b), y, vy, c), z, vz, d) => {
            T(R, Box::new(T(B, a, x, vx, b)), y, vy, Box::new(T(B, c, z, vz, Box::new(d))))
        },

        (B, T(R, a, x, vx, box T(R, b, y, vy, c)), z, vz, d) => {
            T(R, Box::new(T(B, a, x, vx, b)), y, vy, Box::new(T(B, c, z, vz, Box::new(d))))
        },
        (B, a, x, vx, T(R, box T(R, b, y, vy, c), z, vz, d)) => {
            T(R, Box::new(T(B, Box::new(a), x, vx, b)), y, vy, Box::new(T(B, c, z, vz, d)))
        },
        (B, a, x, vx, T(R, b, y, vy, box T(R, c, z, vz, d))) => {
            T(R, Box::new(T(B, Box::new(a), x, vx, b)), y, vy, Box::new(T(B, c, z, vz, d)))
        },
        (rb, a, x, vx, b) => T(rb, Box::new(a), x, vx, Box::new(b)),
    }
}

pub(crate) fn insert(key: i32, val: i32, t: Tree) -> Tree {
    fn ins(x: i32, vx: i32, s: Tree) -> Tree {
        match (x, vx, s) {
            (x, vx, E) => T(R, Box::new(E), x, vx, Box::new(E)),
            (x, vx, T(rb, box a, y, vy, box b)) => {
                if x < y {
                    balance(rb, ins(x, vx, a), y, vy, b)
                } else if y < x {
                    balance(rb, a, y, vy, ins(x, vx, b))
                } else {
                    T(rb, Box::new(a), y, vx, Box::new(b))
                }
            },
        }
    }
    blacken(ins(key, val, t))
}

pub(crate) fn bespoke<R: Rng>(n: usize, g: &mut R) -> Tree {
    let sz = choose(1, n + 1, g);
    let kvs = gen_kvs(sz, g);
    kvs.iter().fold(E, |t, (k, v)| insert(*k, *v, t))
}

impl<R: Rng> Arbitrary<R> for Tree {
    fn generate(r: &mut R, n: usize) -> Self {
        bespoke((n as f64).log10() as usize, r)
    }
}

impl<R: Rng> Mutate<R> for Tree {
    fn mutate(&self, r: &mut R, n: usize) -> Self {
        // Get all the keys
        let kvs = elems(self);
        // Mutate the vec
        let kvs = kvs.mutate(r, n);
        kvs.iter().fold(E, |t, (k, v)| insert(*k, *v, t))
    }
}
