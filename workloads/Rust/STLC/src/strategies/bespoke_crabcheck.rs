use crabcheck::quickcheck::Mutate;

use {
    crabcheck::quickcheck::Arbitrary,
    rand::Rng,
};

use crate::{
    implementation::{
        Ctx,
        Expr,
        Typ,
        get_typ,
    },
    spec::ExprOpt,
};

impl<R: Rng> Arbitrary<R> for Expr {
    fn generate(r: &mut R, n: usize) -> Self {
        let typ = Typ::generate(r, n);
        gen_exact_expr(vec![typ.clone()], typ, r, n)
    }
}

fn gen_exact_expr<R: Rng>(ctx: Ctx, t: Typ, r: &mut R, size: usize) -> Expr {
    if size == 0 {
        let mut gens: Vec<Box<dyn Fn(&mut R) -> Expr>> =
            vec![Box::new(|g| gen_one(&ctx, &t.clone(), g))];

        if let Some(var_gen) = gen_var(&ctx, &t, r) {
            gens.push(Box::new(move |_| var_gen.clone()));
        }
        let idx = r.random_range(0..gens.len());
        gens[idx](r)
    } else {
        let mut gens: Vec<Box<dyn Fn(&mut R) -> Expr>> =
            vec![Box::new(|g| gen_one(&ctx, &t, g)), Box::new(|g| gen_app(&ctx, &t, g, size))];
        if let Typ::TFun(box t1, box t2) = &t {
            gens.push(Box::new(|g| gen_abs(&ctx, t1.clone(), t2.clone(), g, size - 1)));
        }
        if let Some(var_gen) = gen_var(&ctx, &t, r) {
            gens.push(Box::new(move |_| var_gen.clone()));
        }
        let idx = r.random_range(0..gens.len());
        gens[idx](r)
    }
}

fn gen_one<R: Rng>(ctx: &Ctx, t: &Typ, r: &mut R) -> Expr {
    match t {
        Typ::TBool => Expr::Bool(bool::generate(r, 0)),
        Typ::TFun(t1, t2) => {
            let mut ctx1 = ctx.clone();
            ctx1.insert(0, *t1.clone());
            let e = gen_one(&ctx1, t2, r);
            Expr::Abs(*t1.clone(), Box::new(e))
        },
    }
}

fn gen_abs<R: Rng>(ctx: &Ctx, t1: Typ, t2: Typ, r: &mut R, size: usize) -> Expr {
    let mut ctx1 = ctx.clone();
    ctx1.insert(0, t1.clone());
    let e = gen_exact_expr(ctx1, t2.clone(), r, size);
    Expr::Abs(t1, Box::new(e))
}

fn gen_app<R: Rng>(ctx: &Ctx, t: &Typ, r: &mut R, size: usize) -> Expr {
    let t_prime = Typ::generate(r, size / 2);
    let e1 = gen_exact_expr(
        ctx.clone(),
        Typ::TFun(Box::new(t_prime.clone()), Box::new(t.clone())),
        r,
        size / 2,
    );
    let e2 = gen_exact_expr(ctx.clone(), t_prime.clone(), r, size / 2);
    Expr::App(Box::new(e1), Box::new(e2))
}

fn gen_var<R: Rng>(ctx: &Ctx, t: &Typ, r: &mut R) -> Option<Expr> {
    let candidates: Vec<usize> =
        ctx.iter().enumerate().filter_map(|(i, t2)| if t2 == t { Some(i) } else { None }).collect();

    if candidates.is_empty() {
        return None;
    }

    let idx = r.random_range(0..candidates.len());
    Some(Expr::Var(candidates[idx] as i32))
}

pub fn frequency<T, R: Rng>(choices: Vec<(usize, Box<dyn Fn(&mut R) -> T>)>, rng: &mut R) -> T
where
{
    let total = choices.iter().map(|(weight, _)| weight).sum::<usize>();
    let mut choice = rng.random_range(0..total);

    for (weight, f) in choices {
        if choice < weight {
            return f(rng);
        }
        choice -= weight;
    }

    unreachable!()
}

fn gen_typ<R: Rng>(r: &mut R, size: usize) -> Typ {
    if size == 0 {
        Typ::TBool
    } else {
        frequency(
            vec![
                (1, Box::new(|_| Typ::TBool)),
                (
                    size,
                    Box::new(move |r| {
                        Typ::TFun(Box::new(gen_typ(r, size / 2)), Box::new(gen_typ(r, size / 2)))
                    }),
                ),
            ],
            r,
        )
    }
}

impl<R: Rng> Arbitrary<R> for Typ {
    fn generate(r: &mut R, n: usize) -> Self {
        let size = n.min(5);
        gen_typ(r, size)
    }
}

impl<R: Rng> Arbitrary<R> for ExprOpt {
    fn generate(r: &mut R, n: usize) -> Self {
        let typ = Typ::generate(r, n);
        let expr = gen_exact_expr(vec![], typ, r, n);
        ExprOpt(Some(expr))
    }
}

impl<R: Rng> Mutate<R> for Expr {
    fn mutate(&self, r: &mut R, _size: usize) -> Self {
        // get the type of the expression
        let typ = get_typ(&vec![], self).expect("should never mutate an ill-typed expression");
        let size = self.size();
        let size = size.mutate(r, 3);
        gen_exact_expr(vec![], typ, r, size)
    }
}

impl<R: Rng> Mutate<R> for ExprOpt {
    fn mutate(&self, r: &mut R, _size: usize) -> Self {
        match &self.0 {
            Some(e) => {
                let typ = get_typ(&vec![], e).expect("should never mutate an ill-typed expression");
                let size = e.size();
                let size = size.mutate(r, 3);
                let expr = gen_exact_expr(vec![], typ, r, size);
                ExprOpt(Some(expr))
            },
            None => unreachable!("should never mutate a failing expression generation"),
        }
    }
}

// #[cfg(test)]
// mod tests {
//     use super::*;
//     use crate::implementation::Expr;
//     use quickcheck::quickcheck;

//     #[test]
//     fn test_gen_zero1() {
//         let t = Typ::TBool;
//         let ctx: Ctx = vec![];
//         let mut g = quickcheck::Gen::new(0);
//         let expr = gen_zero(ctx, t, &mut g);
//         assert!(expr == Some(Expr::Bool(true)) || expr == Some(Expr::Bool(false)));
//     }

//     #[test]
//     fn test_gen_zero2() {
//         let t = Typ::TFun(Box::new(Typ::TBool), Box::new(Typ::TBool));
//         let ctx: Ctx = vec![];
//         let mut g = quickcheck::Gen::new(1);
//         let expr = gen_zero(ctx, t, &mut g);
//         assert!(
//             expr == Some(Expr::Abs(Typ::TBool, Box::new(Expr::Bool(true))))
//                 || expr == Some(Expr::Abs(Typ::TBool, Box::new(Expr::Bool(false))))
//         );
//     }

//     #[test]
//     fn test_gen_expr1() {
//         let t = Typ::TFun(Box::new(Typ::TBool), Box::new(Typ::TBool));
//         let ctx: Ctx = vec![];
//         let mut g = quickcheck::Gen::new(1);
//         let expr = gen_expr(ctx, t, &mut g, 1);
//         assert!(expr.is_some());
//     }

//     #[test]
//     fn test_gen_expr2() {
//         let t = Typ::TFun(Box::new(Typ::TBool), Box::new(Typ::TBool));
//         let ctx: Ctx = vec![
//             Typ::TBool,
//             Typ::TFun(Box::new(Typ::TBool), Box::new(Typ::TBool)),
//         ];
//         let mut g = quickcheck::Gen::new(5);
//         let expr = gen_expr(ctx, t, &mut g, 5);
//         // expr should have a `Var`
//         fn count_vars(expr: &Expr) -> usize {
//             match expr {
//                 Expr::Var(_) => 1,
//                 Expr::Abs(_, body) => count_vars(body),
//                 Expr::App(func, arg) => count_vars(func) + count_vars(arg),
//                 Expr::Bool(_) => 0,
//             }
//         }
//         let var_count = expr.as_ref().map_or(0, |e| count_vars(e));
//         assert!(
//             var_count > 0,
//             "Generated expression should contain at least one variable"
//         );
//         println!("Generated expression: {}", expr.unwrap());
//     }
// }
