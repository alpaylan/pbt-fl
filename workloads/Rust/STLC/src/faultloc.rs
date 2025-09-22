use {
    crabcheck::profiling::quickcheck,
    stlc::{
        spec,
        spec::ExprOpt,
    },
};

fn main() {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() < 3 {
        eprintln!("Usage: {} <tool> <property>", args[0]);
        eprintln!("Available tools: quickcheck");
        eprintln!("Available properties: SinglePreserve, MultiPreserve");
        return;
    }
    let tool = args[1].as_str();
    let property = args[2].as_str();

    let num_tests = 200_000_000;

    let result = match (tool, property) {
        ("crabcheck", "SinglePreserve") => {
            quickcheck(spec::prop_single_preserve as fn(ExprOpt) -> Option<bool>)
        },
        ("crabcheck", "MultiPreserve") => {
            quickcheck(spec::prop_multi_preserve as fn(ExprOpt) -> Option<bool>)
        },
        _ => {
            panic!("Unknown tool or property: {} {}", tool, property)
        },
    };

    println!("{:?}", result);
}
