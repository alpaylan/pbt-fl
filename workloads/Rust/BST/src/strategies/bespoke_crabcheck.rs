use {
    crabcheck::quickcheck::{
        Arbitrary,
        Mutate,
    },
    rand::Rng,
};

use crate::implementation::Tree;

fn gen_tree<R: Rng>(r: &mut R, size: u32, lo: i32, hi: i32) -> Tree {
    if size == 0 || hi - lo <= 1 {
        return Tree::E;
    }
    let k = r.random_range(lo + 1..hi);
    let left = gen_tree(r, size - 1, lo, k);
    let right = gen_tree(r, size - 1, k + 1, hi);
    Tree::T(Box::new(left), k, k, Box::new(right))
}

impl<R: Rng> Arbitrary<R> for Tree {
    fn generate(r: &mut R, n: usize) -> Self {
        gen_tree(r, (n as f32).log2() as u32, -(n as i32), n as i32)
    }
}

fn mut_tree<R: Rng>(rng: &mut R, t: &Tree, n: usize, lo: i32, hi: i32) -> Tree {
    if n == 0 || hi <= lo + 1 {
        return Tree::E;
    }
    match t {
        Tree::E => Tree::E,
        Tree::T(l, k, v, r) => {
            let choice = rng.random_range(0..=3);
            match choice {
                0 => {
                    // just mutate the value
                    let new_v = v.mutate(rng, n);
                    Tree::T(l.clone(), *k, new_v, r.clone())
                },
                1 => {
                    // mutate the key between the left and right
                    let left_root =
                        if let Tree::T(_, k, _, _) = l.as_ref() { *k } else { i32::MIN.max(lo) };

                    let right_root =
                        if let Tree::T(_, k, _, _) = r.as_ref() { *k } else { i32::MAX.min(hi) };

                    if left_root + 1 >= right_root {
                        return Tree::E;
                    }

                    let new_k = rng.random_range(left_root + 1..right_root);
                    Tree::T(l.clone(), new_k, *v, r.clone())
                },
                2 => {
                    // mutate the left tree
                    let new_l = mut_tree(rng, &l, n - 1, lo, *k);
                    Tree::T(Box::new(new_l), *k, *v, r.clone())
                },
                _ => {
                    // mutate the right tree
                    let new_r = mut_tree(rng, &r, n - 1, *k + 1, hi);
                    Tree::T(l.clone(), *k, *v, Box::new(new_r))
                },
            }
        },
    }
}

impl<R: Rng> Mutate<R> for Tree {
    fn mutate(&self, rng: &mut R, n: usize) -> Self {
        mut_tree(rng, self, n, i32::MIN, i32::MAX)
    }
}
